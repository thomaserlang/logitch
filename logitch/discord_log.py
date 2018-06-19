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

class Client(discord.Client):

    conn = None

    async def on_socket_response(self, data):
        if data['op'] != 0:
            return
        msg = data['d']

        if data['t'] == 'MESSAGE_CREATE':
            if 'content' not in msg:
                return
            await self.conn.execute(sa.sql.text('''
                INSERT INTO discord_entries 
                    (id, server_id, channel_id, created_at, message, attachments, user, user_id, user_discriminator, member_nick) VALUES
                    (:id, :server_id, :channel_id, :created_at, :message, :attachments, :user, :user_id, :user_discriminator, :member_nick);
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
                'member_nick': msg['member']['nick'] if 'nick' in msg['member'] else None
            })

        elif data['t'] == 'MESSAGE_UPDATE':
            if 'content' not in msg:
                return
            await self.conn.execute(sa.sql.text('''
                INSERT INTO discord_entry_versions 
                    (entry_id, created_at, message, attachments) 
                SELECT 
                    id, ifnull(updated_at, created_at), message, attachments
                FROM discord_entries WHERE id=:id;
            '''
            ), {
                'id': msg['id'],
            })
            await self.conn.execute(sa.sql.text('''
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
            await self.conn.execute(sa.sql.text('''
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

    async def email_login(self, email, password):
        payload = {
            'email': email,
            'password': password
        }

        from discord.http import Route
        from discord.errors import HTTPException, LoginFailure
        try:
            data = await self.http.request(Route('POST', '/auth/login'), json=payload)
        except HTTPException as e:
            if e.response.status == 400:
                raise LoginFailure('Improper credentials have been passed.') from e
            raise
        return data['token']

async def start(loop):
    client = Client()
    client.conn = sa.create_engine(config['sql_url'],
        convert_unicode=True,
        echo=False,
        pool_recycle=3599,
        encoding='UTF-8',
        connect_args={'charset': 'utf8mb4'},
        strategy=ASYNCIO_STRATEGY,
    )
    if config['discord']['token']:
        loop.create_task(client.start(
            config['discord']['token'], 
            bot=config['discord']['bot'],
        ))
    elif config['discord']['email'] and config['discord']['password']:
        token = await client.email_login(
            config['discord']['email'], 
            config['discord']['password'],
        )
        loop.create_task(client.start(
            token,
            bot=False,
        ))
    else:
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
    loop.create_task(start(loop))
    loop.run_forever()
