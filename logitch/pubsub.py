import asyncio
import websockets
import functools
import requests
import logging
import random, json
import sqlalchemy as sa
from datetime import datetime

from logitch import config

class Pubsub():

    def __init__(self, url, channels, token):
        self.url = url
        self.channels = channels
        self.channel_lookup = {}
        self.token = token
        self.ping_callback = None
        self.pong_check_callback = None
        self.ws = None
        self.loop = asyncio.get_event_loop()
        self.conn = sa.create_engine(config['sql_url'],
            convert_unicode=True,
            echo=False,
            pool_recycle=3599,
            encoding='UTF-8',
            connect_args={'charset': 'utf8mb4'},
        )

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
            if m['data']['type'] == 'chat_login_moderation':
                await self.log_mod_action(message['data']['topic'], m['data'])

    async def log_mod_action(self, topic, data):
        if data['moderation_action'] not in ['ban', 'timeout', 'unban']:
            return
        c = topic.split('.')
        self.conn.execute(sa.sql.text('''
            INSERT INTO entries (type, created_at, channel, room_id, user, user_id, message) VALUES
                (:type, :created_at, :channel, :room_id, :user, :user_id, :message)
        '''), {
            'type': 100,
            'created_at': datetime.utcnow(),
        'channel': self.channel_lookup[c[2]],
            'room_id': c[2],
            'user': data['args'][0],
            'user_id': data['target_user_id'],
            'message': 'Mod action by {}[{}]: {} {}'.format(
                data['created_by'], 
                data['created_by_user_id'],
                data['moderation_action'],
                ' '.join(data['args'])
            ),
        }) 

    async def run(self):
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
        channel_ids = self.lookup_channel_ids()
        current_user_id = self.get_current_user_id()

        for cid, cname in zip(channel_ids, self.channels):
            self.channel_lookup[cid] = cname

        topics = []
        for id_ in channel_ids:
            topics.append('chat_moderator_actions.{}.{}'.format(
                current_user_id,
                id_,
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

    def lookup_channel_ids(self):
        response = requests.get('https://api.twitch.tv/helix/users', 
            params={
                'login': self.channels,
            },
            headers={
                'Authorization': 'Bearer {}'.format(self.token),
            },
        )
        if response.status_code != 200:
            raise Exception(response.text)
        return [r['id'] for r in response.json()['data']]

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

def main():
    app = Pubsub(
        url=config['pubsub_url'],
        channels=config['channels'],
        token=config['token'],
    )
    return app