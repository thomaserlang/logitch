import asyncio, websockets, functools, requests, logging, random, json
from datetime import datetime
from logitch import config, db

class Pubsub():

    def __init__(self, url, token):
        self.url = url
        self.channels = []
        self.channel_lookup = {}
        self.token = token
        self.ping_callback = None
        self.pong_check_callback = None
        self.ws = None
        self.loop = asyncio.get_event_loop()

    async def parse_message(self, message):
        logging.debug(message)
        if message['type'] == 'PONG':
            asyncio.ensure_future(self.ping())
            if self.pong_check_callback:
                self.pong_check_callback.cancel()
        elif message['type'] == 'RECONNECT':
            await self.ws.close()
        elif message['type'] == 'MESSAGE':
            m = json.loads(message['data']['message'])
            self.loop.create_task(self.log_mod_action(message['data']['topic'], m['data']))

    async def log_mod_action(self, topic, data):
        if 'moderation_action' not in data:
            return
        c = topic.split('.')
        try:
            await self.db.execute('''
                INSERT INTO modlogs (created_at, channel_id, channel, user, user_id, command, args, target_user, target_user_id) VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ''', (
                datetime.utcnow(),
                c[2],
                self.channel_lookup[int(c[2])],
                data['created_by'],
                data['created_by_user_id'],
                data['moderation_action'],
                ' '.join(data['args']).strip() if data['args'] else '',
                data['args'][0] if data['target_user_id'] else None,
                data['target_user_id'] if data['target_user_id'] else None,
            )) 

            if data['target_user_id']:
                await self.db.execute('''
                    INSERT INTO entries (type, created_at, channel, channel_id, user, user_id, message) VALUES
                        (%s, %s, %s, %s, %s, %s, %s)
                ''', (
                    100,
                    datetime.utcnow(),
                    self.channel_lookup[int(c[2])],
                    c[2],
                    data['args'][0],
                    data['target_user_id'],
                    '<{}{} (by {})>'.format(
                        data['moderation_action'],
                        ' '+' '.join(data['args']).strip() if data['args'] else '',
                        data['created_by'],
                    ),
                )) 
        except:
            logging.exception('log_mod_action')

    async def run(self):
        self.db = await db.Db().connect(self.loop)
        while True:
            if self.ws:
                self.ws.close()
            try:
                await self.connect()
                while True:
                    try:
                        message = await self.ws.recv()
                        await self.parse_message(json.loads(message))
                    except websockets.exceptions.ConnectionClosed:
                        logging.info('PubSub connection closed')
                        self.ping_callback.cancel()
                        break
                    except KeyboardInterrupt:
                        raise KeyboardInterrupt()
                    except:
                        logging.exception('Loop 2')
            except KeyboardInterrupt:
                break
            except:
                logging.exception('Loop 1')
                await asyncio.sleep(10)

    async def connect(self):
        if self.ping_callback:
            self.ping_callback.cancel()
        current_user_id = self.get_current_user_id()
        self.channels = await self.get_channels() 
        topics = []
        for c in self.channels:
            self.channel_lookup[c['channel_id']] = c['name']
            topics.append('chat_moderator_actions.{}.{}'.format(
                current_user_id,
                c['channel_id'],
            ))
        logging.info('PubSub Connecting to {}'.format(config['pubsub_url']))
        self.ws = await websockets.connect(config['pubsub_url'])
        await self.ws.send(json.dumps({
            'type': 'LISTEN',
            'data': {
                'topics': topics,
                'auth_token': config['token'],
            }
        }))
        self.ping_callback = asyncio.ensure_future(self.ping())

    async def ping(self):
        await asyncio.sleep(random.randint(120, 240))
        await self.ws.send('{"type": "PING"}')
        self.pong_check_callback = asyncio.ensure_future(self.close())

    async def close(self):
        await asyncio.sleep(10)
        logging.info('closing')
        await self.ws.close()

    def get_current_user_id(self):
        response = requests.get('https://api.twitch.tv/helix/users', 
            headers={
                'Authorization': 'Bearer {}'.format(self.token),
            },
        )
        if response.status_code != 200:
            raise Exception(response.text)
        data = response.json()
        ids = []
        return response.json()['data'][0]['id']

    async def get_channels(self):
        rows = await self.db.fetchall('SELECT channel_id, name FROM channels WHERE active="Y";')
        l = []
        for r in rows:
            l.append({
                'channel_id': r['channel_id'],
                'name': r['name'].lower(),
            })
        return l

def main():
    app = Pubsub(
        url=config['pubsub_url'],
        token=config['token'],
    )
    return app

if __name__ == '__main__':
    from logitch import config_load, logger
    config_load()    
    logger.set_logger('pubsub.log')
    loop = asyncio.get_event_loop()
    loop.create_task(main().run())    
    loop.run_forever()