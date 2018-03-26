import bottom, asyncio, logging
import sqlalchemy as sa
from datetime import datetime
from logitch.irc.unpack import rfc2812_handler
from logitch import config

bot = bottom.Client('a', 0)

@bot.on('CLIENT_CONNECT')
async def connect(**kwargs):
    logging.info('Connecting')
    if config['irc']['password']:
        bot.send('PASS', password=config['irc']['password'])
    bot.send('NICK', nick=config['irc']['username'])
    bot.send('USER', user=config['irc']['username'], realname=config['irc']['username'])

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

    for channel in config['irc']['channels']:
        bot.send('JOIN', channel='#'+channel.strip('#'))

@bot.on('PING')
def keepalive(message, **kwargs):
    bot.send('PONG', message=message)

@bot.on('PRIVMSG')
def message(nick, target, message, **kwargs):
    save(1, target, kwargs['room-id'], nick, kwargs['user-id'], message)

@bot.on('CLEARCHAT')
def clearchat(channel, banned_user, **kwargs):
    if 'ban-reason' not in kwargs:
        return
    type_ = 2
    if 'ban-duration' in kwargs:
        type_ = 3
        if kwargs['ban-duration'] == '1':
            type_ = 4
    save(type_, channel, kwargs['room-id'], banned_user, kwargs['target-user-id'], kwargs['ban-reason'])

def save(type_, channel, room_id, user, user_id, message):
    logging.debug('{} {} {} {}'.format(type_, channel, user, message))
    try:
        bot.conn.execute(sa.sql.text('''
            INSERT INTO entries (type, created_at, channel, room_id, user, user_id, message) VALUES
                (:type, :created_at, :channel, :room_id, :user, :user_id, :message)
        '''), {
            'type': type_,
            'created_at': datetime.utcnow(),
            'channel': channel[1:],
            'room_id': room_id,
            'user': user,
            'user_id': user_id,
            'message': message,
        })
    except:
        logging.exception('sql')

def main():
    bot.host = config['irc']['host'] 
    bot.port = config['irc']['port'] 
    bot.ssl = config['irc']['use_ssl']
    bot.raw_handlers = [rfc2812_handler(bot)]
    bot.conn = sa.create_engine(config['irc']['sql_url'],
        convert_unicode=True,
        echo=False,
        pool_recycle=3599,
        encoding='UTF-8',
        connect_args={'charset': 'utf8mb4'},
    )
    bot.loop.create_task(bot.connect())
    bot.loop.run_forever()

if __name__ == '__main__':
    from logitch import config_load, logger
    config_load()    
    logger.set_logger('irc.log')
    main()
    