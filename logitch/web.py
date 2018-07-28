import logging, json, os
from tornado import web, ioloop, httpclient, escape
from urllib import parse
from logitch import config, db

class Base_handler(web.RequestHandler):

    @property
    def db(self):
        return self.application.db

class Authenticated_handler(Base_handler):

    def get_current_user(self):
        data = self.get_secure_cookie('data', max_age_days=0.14)
        if not data:
            return
        return json.loads(escape.native_str(data))

class Handler(Authenticated_handler):

    @web.authenticated
    async def get(self):
        mod_of_channels = await self.get_mod_of_channels()
        channel = self.get_argument('channel', '').lower()
        channel_id = self.get_argument('channel_id', None)
        user = self.get_argument('user', '').lower()
        context = self.get_argument('context', None)
        message = self.get_argument('message', '')
        show_mod_actions_only = self.get_argument('show-mod-actions-only', None)
        logs = []
        sql = None
        args = []
        user_stats = None

        if channel:
            channel_id = await self.get_channel_id(channel)
            if not channel_id:                
                raise web.HTTPError(404, 'Unknown channel')
        if channel_id:
            if channel_id not in mod_of_channels:
                raise web.HTTPError(403, 'You are not a moderator of this channel')
            sql = 'channel_id=%s'
            args.append(channel_id)
            if user:
                user_stats = await self.get_user_stats(channel_id, user)
                sql += ' AND user_id=%s'
                args.append(user_stats['user_id'] if user_stats else 0)
            if context:
                sql += ' AND created_at<=%s'
                args.append(context)
            if show_mod_actions_only == 'yes':
                sql += ' AND type=100'
            if message:
                sql += ' AND message LIKE %s'
                args.append('%' + message + '%')
            if sql:
                logs = await self.db.fetchall(
                    'SELECT id, created_at, type, user, message FROM entries WHERE '+sql+' ORDER BY id DESC LIMIT 100;', 
                    args
                )
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

    async def get_mod_of_channels(self):
        rows = await self.db.fetchall(
            '''SELECT c.channel_id, c.name FROM mods m, channels c WHERE 
                m.user_id=%s AND 
                c.channel_id=m.channel_id AND
                c.active='Y';
            ''', 
            (self.current_user['user_id'],)
        )
        return {r['channel_id']: r['name'] for r in rows}

    async def get_user_stats(self, channel_id, user):
        q = await self.db.fetchone(
            '''
                SELECT 
                    un.user_id,
                    us.bans,
                    us.timeouts,
                    us.purges,
                    us.chat_messages
                FROM 
                    usernames un, user_stats us 
                WHERE 
                    un.user=%s AND 
                    us.channel_id=%s AND
                    us.user_id=un.user_id;
            ''', (user, channel_id)
        )
        return q

    async def get_channel_id(self, channel):
        r = await self.db.fetchone(
            'SELECT channel_id FROM channels WHERE name=%s;', 
            (channel,)
        )
        if not r:
            return
        return r['channel_id']

class Login_handler(Authenticated_handler):

    def get(self):
        if self.current_user:
            self.redirect('/')
            return
        _next = self.get_argument('next', None)
        if _next:
            self.set_secure_cookie('next', _next)
        auto_login = escape.native_str(self.get_secure_cookie('auto_login'))
        if auto_login == 'true':
            self.signin()
            return
        self.render('login.html')

    def post(self):
        if self.current_user:
            self.redirect('/')
        else:
            self.signin()

    def signin(self):
        self.redirect('https://id.twitch.tv/oauth2/authorize?'+parse.urlencode({
                'client_id': config['client_id'],
                'response_type': 'code',
                'redirect_uri': config['redirect_uri'],
                'scope': '',
            })
        )

class Logout_handler(Base_handler):

    def get(self):
        self.clear_cookie('data')
        self.clear_cookie('auto_login')
        self.redirect('/login')

class OAuth_handler(Base_handler):

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
            self.clear_cookie('data')
            self.clear_cookie('auto_login')
            self.write('Unable to verify you at Twitch, <a href="/login">please try again.</a>')
            return
        userinfo = json.loads(escape.native_str(response.body))
        self.set_secure_cookie('data', json.dumps({
            'user_id': userinfo['user_id'],
            'user': userinfo['login'],
            'access_token': token['access_token'],
        }), expires_days=None)
        self.set_secure_cookie('auto_login', 'true', expires_days=31)
        _next = self.get_secure_cookie('next')
        if _next:
            self.redirect(_next)
        else:
            self.redirect('/')

class User_suggest_handler(Authenticated_handler):

    async def post(self):
        rows = await self.db.fetchall(
            'SELECT user, user_id FROM usernames WHERE user LIKE %s LIMIT 5;', 
            (self.get_argument('phrase')+'%',)
        )
        users = []
        for r in rows:
            users.append({
                'user': r['user'],
                'id': r['user_id'],
            })
        self.write(json.dumps(users))

    def set_default_headers(self):
        self.set_header('Cache-Control', 'no-cache, must-revalidate')
        self.set_header('Expires', 'Sat, 26 Jul 1997 05:00:00 GMT')

def App():
    return web.Application(
        [
            (r'/', Handler),
            (r'/login', Login_handler),
            (r'/logout', Logout_handler),
            (r'/oauth', OAuth_handler),
            (r'/user-suggest', User_suggest_handler),
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
    loop = ioloop.IOLoop.current()
    loop.add_callback(db_connect, app)
    loop.start()

async def db_connect(app):
    app.db = await db.Db().connect(None)

if __name__ == '__main__':
    from logitch import config_load, logger
    config_load()
    logger.set_logger('web.log')
    main()