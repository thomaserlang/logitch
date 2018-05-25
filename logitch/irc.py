import bottom, asyncio, logging, random, aiohttp
import sqlalchemy as sa
from sqlalchemy_aio import ASYNCIO_STRATEGY
from datetime import datetime
from logitch.unpack import rfc2812_handler
from logitch import config

bot = bottom.Client('a', 0)

@bot.on('CLIENT_CONNECT')
async def connect(**kwargs):
    if not bot.http_session:
        bot.http_session = aiohttp.ClientSession()

    if bot.pong_check_callback:
        bot.pong_check_callback.cancel()
    logging.info('IRC Connecting to {}:{}'.format(config['irc']['host'], config['irc']['port']))
    if config['token']:
        bot.send('PASS', password='oauth:{}'.format(config['token']))
    bot.send('NICK', nick=config['user'])
    bot.send('USER', user=config['user'], realname=config['user'])

    # Don't try to join channels until the server has
    # sent the MOTD, or signaled that there's no MOTD.
    done, pending = await asyncio.wait(
        [bot.wait("RPL_ENDOFMOTD"),
         bot.wait("ERR_NOMOTD")],
        loop=bot.loop,
        return_when=asyncio.FIRST_COMPLETED
    )

    bot.send_raw('CAP REQ :twitch.tv/tags')
    bot.send_raw('CAP REQ :twitch.tv/commands')
    bot.send_raw('CAP REQ :twitch.tv/membership')

    # Cancel whichever waiter's event didn't come in.
    for future in pending:
        future.cancel()

    for channel in config['channels']:
        bot.send('JOIN', channel='#'+channel)
        bot.send("PRIVMSG", target='#'+channel, message='/mods')

    if bot.pong_check_callback:
        bot.pong_check_callback.cancel()
    if bot.ping_callback:
        bot.ping_callback.cancel()
    bot.ping_callback = asyncio.ensure_future(send_ping())

async def send_ping():
    await asyncio.sleep(random.randint(120, 240))
    logging.debug('Sending ping')
    bot.pong_check_callback = asyncio.ensure_future(wait_for_pong())
    bot.send('PING')

async def wait_for_pong():
    await asyncio.sleep(10)
    logging.error('Didn\'t receive a PONG in time, reconnecting')
    if bot.ping_callback:
        bot.ping_callback.cancel()
    bot.ping_callback = asyncio.ensure_future(send_ping())
    await bot.connect()

@bot.on('CLIENT_DISCONNECT')
async def disconnect(**kwargs):
    logging.info('Disconnected')

@bot.on('PING')
def keepalive(message, **kwargs):
    logging.debug('Received ping, sending PONG back')
    bot.send('PONG', message=message)

@bot.on('PONG')
async def pong(message, **kwargs):
    logging.debug('Received pong')
    if bot.pong_check_callback:
        bot.pong_check_callback.cancel()
    if bot.ping_callback:
        bot.ping_callback.cancel()
    bot.ping_callback = asyncio.ensure_future(send_ping())

@bot.on('PRIVMSG')
async def message(nick, target, message, **kwargs):
    bot.loop.create_task(
        save(1, target, kwargs['room-id'], nick, kwargs['user-id'], message)
    )

    if not message.startswith('!'):
        return

    is_mod = kwargs['mod'] == '1' or nick == target.strip('#')
    if is_mod and message == '!updatemods':
        bot.send("PRIVMSG", target=target, message='/mods')
        bot.send("PRIVMSG", target=target, message='Affirmative, {}'.format(nick))

@bot.on('CLEARCHAT')
async def clearchat(channel, banned_user, **kwargs):
    if 'ban-reason' not in kwargs:
        return
    type_ = 2
    reason = kwargs['ban-reason'] or 'empty'
    message = '<Banned. Reason: {}>'.format(reason)
    if 'ban-duration' in kwargs:
        type_ = 3
        message = '<Timeout. Duration: {}. Reason: {}>'.format(kwargs['ban-duration'], reason)
        if kwargs['ban-duration'] == '1':
            message = '<Purge. Reason: {}>'.format(reason)
            type_ = 4
    bot.loop.create_task(
        save(type_, channel, kwargs['room-id'], banned_user, kwargs['target-user-id'], message)
    )

@bot.on('NOTICE')
async def notice(target, message, **kwargs):
    logging.debug('NOTICE: {}'.format(message))
    if 'msg-id' not in kwargs:
        return

    if kwargs['msg-id'] == 'room_mods':
        bot.loop.create_task(save_mods(target, message))

async def save_mods(target, message):
    a = message.split(':')
    channel = target.strip('#')
    if len(a) == 2:
        mods = [b.strip() for b in a[1].split(',')]
    else:
        mods = []
    mods.append(channel)

    users = await lookup_usernames(mods)
    if users == None:
        return
    data = []
    for u in users:
        data.append({
            'channel': channel,
            'user_id': u['id'],
            'user': u['user'],
        })
    await bot.conn.execute(sa.sql.text('DELETE FROM mods WHERE channel=:channel;'), {
        'channel': channel,
    })
    await bot.conn.execute(
        sa.sql.text('INSERT INTO mods (channel, user_id, user) VALUES (:channel, :user_id, :user);'), 
        data
    )

async def lookup_usernames(usernames):
    url = 'https://api.twitch.tv/helix/users'
    params = [('login', name) for name in usernames]
    headers = {'Authorization': 'Bearer {}'.format(config['token'])}
    async with bot.http_session.get(url, params=params, headers=headers) as r:
        if r.status != 200:
            return None
        data = await r.json()
        users = []
        for d in data['data']:
            users.append({'id': d['id'], 'user': d['login']})
        return users

def send_whisper(nick, target, message):
    bot.send('PRIVMSG', target=target, message='/w {} {}'.format(nick, message))

async def save(type_, channel, room_id, user, user_id, message):
    logging.debug('{} {} {} {}'.format(type_, channel, user, message))
    try:
        await bot.conn.execute(sa.sql.text('''
            INSERT INTO entries (type, created_at, channel, room_id, user, user_id, message, word_count) VALUES
                (:type, :created_at, :channel, :room_id, :user, :user_id, :message, :word_count)
        '''), {
            'type': type_,
            'created_at': datetime.utcnow(),
            'channel': channel[1:],
            'room_id': room_id,
            'user': user,
            'user_id': user_id,
            'message': message,
            'word_count': len(message.split(' ')),
        })
    except:
        logging.exception('sql')

def main():
    bot.host = config['irc']['host'] 
    bot.port = config['irc']['port'] 
    bot.ssl = config['irc']['use_ssl']
    bot.raw_handlers = [rfc2812_handler(bot)]
    bot.conn = sa.create_engine(config['sql_url'],
        convert_unicode=True,
        echo=False,
        pool_recycle=3599,
        encoding='UTF-8',
        connect_args={'charset': 'utf8mb4'},
        strategy=ASYNCIO_STRATEGY,
    )
    bot.http_session = None
    bot.pong_check_callback = None
    bot.ping_callback = None
    return bot

if __name__ == '__main__':
    from logitch import config_load, logger
    config_load()    
    logger.set_logger('irc.log')
    loop = asyncio.get_event_loop()
    loop.create_task(main().connect())    
    loop.run_forever()