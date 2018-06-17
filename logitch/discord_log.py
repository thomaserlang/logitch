import discord
import asyncio
import zlib
import logging
import json
import sqlalchemy as sa
from sqlalchemy_aio import ASYNCIO_STRATEGY
from dateutil.parser import parse
from datetime import datetime
from logitch import config

client = discord.Client()
conn = None

@client.event
async def on_socket_raw_receive(data):
    if isinstance(data, bytes):
        data = zlib.decompress(data, 15, 10490000) # This is 10 MiB
        data = data.decode('utf-8')

    data = json.loads(data)

    if data['op'] != 0:
        return
    msg = data['d']

    if data['t'] == 'MESSAGE_CREATE':
        await conn.execute(sa.sql.text('''
            INSERT INTO discord_entries 
                (id, server_id, channel_id, created_at, message, attachments, user, user_id, user_discriminator) VALUES
                (:id, :server_id, :channel_id, :created_at, :message, :attachments, :user, :user_id, :user_discriminator);
        '''), {
            'id': msg['id'],
            'server_id': msg['guild_id'],
            'channel_id': msg['channel_id'],
            'created_at': parse(msg['timestamp']).replace(tzinfo=None),
            'message': msg['content'],
            'attachments': json.dumps(msg['attachments']) if msg['attachments'] else None,
            'user': msg['author']['username'],
            'user_id': msg['author']['id'],
            'user_discriminator': msg['author']['discriminator'],
        })

    elif data['t'] == 'MESSAGE_UPDATE':
        await conn.execute(sa.sql.text('''
            INSERT INTO discord_entry_versions 
                (entry_id, created_at, message, attachments) 
            SELECT 
                id, ifnull(updated_at, created_at), message, attachments
            FROM discord_entries WHERE id=:id;
        '''
        ), {
            'id': msg['id'],
        })
        await conn.execute(sa.sql.text('''
            UPDATE discord_entries SET 
                updated_at=:updated_at, 
                message=:message, 
                attachments=:attachments
            WHERE
                id=:id;
        '''), {
            'id': msg['id'],
            'message': msg['content'],
            'attachments': json.dumps(msg['attachments']) if msg['attachments'] else None,
            'updated_at': parse(msg['edited_timestamp']).replace(tzinfo=None),
        })
    
    elif data['t'] == 'MESSAGE_DELETE':
        await conn.execute(sa.sql.text('''
            UPDATE discord_entries SET 
                deleted="Y",
                deleted_at=:deleted_at
            WHERE
                id=:id;
        '''
        ), {
            'id': msg['id'],
            'deleted_at': datetime.utcnow(),
        })

@client.event
async def on_ready():
    global conn
    if not conn:
        conn = sa.create_engine(config['sql_url'],
            convert_unicode=True,
            echo=False,
            pool_recycle=3599,
            encoding='UTF-8',
            connect_args={'charset': 'utf8mb4'},
            strategy=ASYNCIO_STRATEGY,
        )

def start():
    if config['discord']['token']:
        return client.start(config['token'])
    elif config['discord']['email'] and config['discord']['password']:
        return client.start(
            config['discord']['email'],
            config['discord']['password']
        )
    raise Exception(
        "Missing login info. "
        "`config['discord']['token']` or "
        "`config['discord']['email']` and "
        "`config['discord']['password']`"
    )

if __name__ == '__main__':
    from logitch import config_load, logger
    config_load()    
    logger.set_logger('discord.log')
    loop = asyncio.get_event_loop()
    loop.create_task(start())    
    loop.run_forever()