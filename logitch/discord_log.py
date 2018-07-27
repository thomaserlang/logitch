try:
    import discord
except ImportError:
    raise Exception('''
        The discord libary must be installed manually:
            pip install https://github.com/Rapptz/discord.py/archive/rewrite.zip
    ''')
import logging, asyncio, json, aiohttp
from dateutil.parser import parse
from datetime import datetime
from logitch import config, db

class Client(discord.Client):

    async def on_connect(self):
        if not hasattr(self, 'ahttp'):
            self.ahttp = aiohttp.ClientSession()
            self.db = await db.Db().connect(self.loop)

    async def on_socket_response(self, data):
        if data['op'] != 0:
            return
        msg = data['d']
        try:
            if data['t'] == 'MESSAGE_CREATE':
                if 'content' not in msg:
                    return
                if msg['type'] != 0:
                    return
                await self.db.execute('''
                    INSERT INTO discord_entries 
                        (id, server_id, channel_id, created_at, message, attachments, user, user_id, user_discriminator, member_nick) VALUES
                        (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s);
                ''', (
                    msg['id'],
                    msg['guild_id'],
                    msg['channel_id'],
                    parse(msg['timestamp']).replace(tzinfo=None),
                    msg['content'],
                    json.dumps(msg['attachments']) if msg['attachments'] else None,
                    msg['author']['username'],
                    msg['author']['id'],
                    msg['author']['discriminator'],
                    msg['member']['nick'] if 'nick' in msg['member'] else None,
                ))
            elif data['t'] == 'MESSAGE_UPDATE':
                if 'content' not in msg:
                    return
                if msg['type'] != 0:
                    return
                await self.db.execute('''
                    INSERT INTO discord_entry_versions 
                        (entry_id, created_at, message, attachments) 
                    SELECT 
                        id, ifnull(updated_at, created_at), message, attachments
                    FROM discord_entries WHERE id=%s;
                ''', (msg['id'],) 
                )
                await self.db.execute('''
                    UPDATE discord_entries SET 
                        updated_at=%s, 
                        message=%s, 
                        attachments=%s
                    WHERE
                        id=%s;
                ''', (
                    parse(msg['edited_timestamp']).replace(tzinfo=None),
                    msg['content'],
                    json.dumps(msg['attachments']) if msg['attachments'] else None,
                    msg['id'],
                ))
            
            elif data['t'] == 'MESSAGE_DELETE':
                await self.db.execute('''
                    UPDATE discord_entries SET 
                        deleted="Y",
                        deleted_at=%s
                    WHERE
                        id=%s;
                    ''', 
                    (datetime.utcnow(), msg['id'],)
                )        
        except:
            logging.exception('on_socket_response')

def main():
    bot = Client()
    bot.run(config['discord']['token'], bot=config['discord']['bot'])

if __name__ == '__main__':
    from logitch import config_load, logger
    config_load()    
    logger.set_logger('discord.log')
    main()