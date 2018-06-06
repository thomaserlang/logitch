import logging
import json
import os
import sqlalchemy as sa
from tornado import web, ioloop, httpclient, escape
from urllib import parse
from logitch import config

class Authenticated_handler(web.RequestHandler):

    def get_current_user(self):
        data = self.get_secure_cookie('data', max_age_days=0.14)
        if not data:
            return
        return json.loads(escape.native_str(data))

class Handler(Authenticated_handler):

    @web.authenticated
    def get(self):
        mod_of_channels = self.get_mod_of_channels()
        channel = self.get_argument('channel', '').lower()
        user = self.get_argument('user', '').lower()
        context = self.get_argument('context', None)
        show_mod_actions_only = self.get_argument('show-mod-actions-only', None)
        logs = []
        sql = None
        args = {}
        user_stats = None
        if channel:
            if channel not in mod_of_channels:
                raise web.HTTPError(403, 'You are not a moderator of this channel')
            sql = 'channel=:channel'
            args['channel'] = channel
        if channel and user:
            user_stats = self.get_user_stats(channel, user)
            sql += ' AND user_id=:user_id'
            args['user_id'] = user_stats['user_id'] if user_stats else 0
        if channel and context:
            sql += ' AND created_at<=:created_at'
            args['created_at'] = context
        if channel and show_mod_actions_only=='yes':
            sql += ' AND type=100'
        if sql and channel:
            logs = self.application.conn.execute(
                sa.sql.text('SELECT id, created_at, type, user, message FROM entries WHERE '+sql+' ORDER BY id DESC LIMIT 100;'), 
                args
            )
            logs = logs.fetchall()
        self.render('logs.html', 
            logs=logs, 
            render_type=self.render_type,
            mod_of_channels=mod_of_channels,
            user_stats=user_stats,
        )

    def render_type(self, type_):
        if type_ == 1:
            return ''
        if type_ == 2:
            return '<span class="badge badge-danger" title="The user was banned by a mod. Reason in message.">B</span>'
        if type_ == 3:
            return '<span class="badge badge-warning" title="The user received a timeout by a mod. Reason in message.">T</span>'
        if type_ == 4:
            return '<span class="badge badge-info" title="The user was purged a by mod. Reason in message.">P</span>'
        if type_ == 100:
            return '<span class="badge badge-success" title="An action by a mod concerning this user.">M</span>'

    def get_mod_of_channels(self):
        q = self.application.conn.execute(
            sa.sql.text('SELECT * FROM mods WHERE user_id=:user_id;'), 
            {'user_id': self.current_user['user_id']}
        )
        rows = q.fetchall()
        return [r['channel'] for r in rows]

    def get_user_stats(self, channel, user):
        q = self.application.conn.execute(
            sa.sql.text('''
                SELECT 
                    un.user_id,
                    us.bans,
                    us.timeouts,
                    us.purges,
                    us.chat_messages
                FROM 
                    usernames un, user_stats us 
                WHERE 
                    un.user=:user AND 
                    us.channel=:channel AND
                    us.user_id=un.user_id;
            '''), 
            {'channel': channel, 'user': user}
        )
        return q.fetchone()

class Login_handler(Authenticated_handler):

    def get(self):
        if self.current_user:
            self.redirect('/')
            return
        _next = self.get_argument('next', None)
        if _next:
            self.set_secure_cookie('next', _next)
        self.render('login.html')

    def post(self):
        if self.current_user:
            self.redirect('/')
        else:
            self.redirect('https://id.twitch.tv/oauth2/authorize?'+parse.urlencode({
                    'client_id': config['client_id'],
                    'response_type': 'code',
                    'redirect_uri': config['redirect_uri'],
                    'scope': '',
                })
            )

class Logout_handler(web.RequestHandler):

    def get(self):
        self.clear_cookie('data')
        self.redirect('/login')

class OAuth_handler(web.RequestHandler):

    async def get(self):
        code = self.get_argument('code')
        http = httpclient.AsyncHTTPClient()
        response = await http.fetch('https://id.twitch.tv/oauth2/token?'+parse.urlencode({
            'client_id': config['client_id'],
            'client_secret': config['client_secret'],
            'code': code,
            'redirect_uri': config['redirect_uri'],
            'grant_type': 'authorization_code',
        }), body='', method='POST', raise_error=False)
        if response.code != 200:
            logging.error(response.body)
            self.write('Unable to verify you at Twitch, please try again.')
            return
        token = json.loads(escape.native_str(response.body))
        response = await http.fetch('https://id.twitch.tv/oauth2/validate', headers={
            'Authorization': 'OAuth {}'.format(token['access_token'])
        })
        if response.code != 200:
            logging.error(response.body)
            self.write('Unable to verify you at Twitch, please try again.')
            return
        userinfo = json.loads(escape.native_str(response.body))
        self.set_secure_cookie('data', json.dumps({
            'user_id': userinfo['user_id'],
            'user': userinfo['login'],
            'access_token': token['access_token'],
        }), expires_days=None)
        _next = self.get_secure_cookie('next')
        if _next:
            self.redirect(_next)
        else:
            self.redirect('/')

def App():
    return web.Application(
        [
            (r'/', Handler),
            (r'/login', Login_handler),
            (r'/logout', Logout_handler),
            (r'/oauth', OAuth_handler),
        ], 
        login_url='/login', 
        debug=config['debug'], 
        cookie_secret=config['cookie_secret'],
        template_path=os.path.join(os.path.dirname(__file__), 'templates'),
        autoescape=None,
    )

def main():
    app = App()
    app.listen(config['web_port'])
    app.conn = sa.create_engine(config['sql_url'],
        convert_unicode=True,
        echo=False,
        pool_recycle=3599,
        encoding='UTF-8',
        connect_args={'charset': 'utf8mb4'},
    )
    ioloop.IOLoop.current().start()

if __name__ == '__main__':
    from logitch import config_load, logger
    config_load()
    logger.set_logger('web.log')
    main()