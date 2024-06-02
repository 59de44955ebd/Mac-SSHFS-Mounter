import base64
import json
import os
import random
import re
import rumps
import subprocess
import sys
import time
import traceback

APP_NAME = 'SSHFS-Mounter'
APP_VERSION = '0.2'

if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.realpath(sys.executable))
    RES_DIR = os.path.realpath(os.path.join(APP_DIR, '..', 'Resources'))
    BIN_DIR = APP_DIR
else:
    APP_DIR = os.path.dirname(os.path.realpath(__file__))
    RES_DIR = os.path.join(APP_DIR, 'resources')
    BIN_DIR = os.path.join(APP_DIR, 'bin')


# Simple XOR encryption of passwords stored in JSON file
# This only prevents reading the passwords directly without having the Python source code
MASTER_KEY = b'uLXdt2@X*eVh5a8194l!4ySFpvkS!2_092Mj21hcJ3W64qJG&rayCg_J3D9$@aO)'

CYBERDUCK_BM_DIR = os.path.join(os.environ['HOME'], 'Library', 'Group Containers', 'G69SCX94XU.duck', 'Library', 'Application Support', 'duck', 'Bookmarks')
FILEZILLA_XML_FILE = os.path.join(os.environ['HOME'], '.config', 'filezilla', 'sitemanager.xml')

MAX_WAIT_CONNECT_SEC = 5
POLL_PERIOD_SEC = .5


class MyApp(rumps.App):

    ########################################
    #
    ########################################
    def __init__(self):
        super().__init__(
                APP_NAME,
                icon=os.path.join(RES_DIR, "app.icns"),
                quit_button=None
                )

        self._debug = False
        self._poll_data = {}
        self._poll_timer = rumps.Timer(self.check_mount, POLL_PERIOD_SEC)

        tmp_dir = f'/tmp/sshfs'
        if not os.path.isdir(tmp_dir):
            os.mkdir(tmp_dir)

        self.connections_json_file = os.path.join(rumps.application_support(self.name), 'connections.json')
        if not os.path.isfile(self.connections_json_file):
            with open(self.connections_json_file, 'w') as f:
                f.write('[]')

        self.load_connections()
        self.create_menu()

    ########################################
    #
    ########################################
    def create_menu(self):
        self.menu.clear()

        menu = []
        for con in self.connection_dict.values():
            mi = rumps.MenuItem(con["name"], callback=self.toggle_connection)
            volname = re.sub(r'[<>:"/\\|?*]', '_', con['name'][:32])
            mount_point = f'/tmp/sshfs/{volname}'
            if os.path.ismount(mount_point):
                mi.state = 1
            menu.append(mi)
        menu.append(None)

        config_menu = []
        config_menu.append(rumps.MenuItem('Edit connections.jsons', callback=self.edit_connection))
        config_menu.append(rumps.MenuItem('Reload connections.json', callback=self.reload_connections))
        has_cyberduck = os.path.isdir(CYBERDUCK_BM_DIR)
        has_filezilla = os.path.isfile(FILEZILLA_XML_FILE)
        if has_cyberduck or has_filezilla:
            config_menu.append(None)
        if has_cyberduck:
            config_menu.append(rumps.MenuItem('Import from Cyberduck', callback=self.import_connections_cyberduck))
        if has_filezilla:
            config_menu.append(rumps.MenuItem('Import from FileZilla', callback=self.import_connections_filezilla))
        config_menu.append(None)
        config_menu.append(rumps.MenuItem('Debug', callback=self.toggle_debug))

        menu.append({'Settings': config_menu})
        menu.append(None)
        menu.append(rumps.MenuItem('Quit', callback=rumps.quit_application))

        self.menu.update(menu)

    ########################################
    #
    ########################################
    def toggle_debug(self, sender):
        sender.state = not sender.state
        self._debug = sender.state

    ########################################
    #
    ########################################
    def edit_connection(self, sender):
        subprocess.call(['open', '-a', 'TextEdit', self.connections_json_file])

    ########################################
    #
    ########################################
    def toggle_connection(self, sender):

        con = self.connection_dict[sender.title]
        volname = re.sub(r'[<>:"/\\|?*]', '_', con['name'][:32])
        mount_point = f'/tmp/sshfs/{volname}'

        if not sender.state:

            if not os.path.isdir(mount_point):
                os.mkdir(mount_point)

            elif os.path.ismount(mount_point):
                # volume already mounted, ignore silently
                sender.state = 1
                subprocess.call(["open", mount_point])
                return

            env = {}

            command = [
                    os.path.join(BIN_DIR, 'sshfs'),
                    f"{con['user']}@{con['host']}:{con['path']}",
                    mount_point,
                    f"-p{con['port']}",
                    f'-ovolname={volname}',
                    "-oStrictHostKeyChecking=no", "-oUserKnownHostsFile=/dev/null",
                    ]

            if self._debug:
                command += ['-odebug', '-ologlevel=debug1']

            if con["auth"] == "key":
                if not os.path.isfile(os.path.expanduser(con['key_file'])):
                    rumps.Window(message='The assigned private key file does not exist:\n\n{}'.format(con['key_file']), dimensions=(320, 0)).run()
                    return
                command += ["-oPreferredAuthentications=publickey", "-oIdentityFile={}".format(con['key_file'])]

            else:
                if con["auth"] == "password":
                    if "password" in con:
                        pw = self._dec(con['password'])
                    else:
                        res = rumps.Window(message='Enter password:', cancel=True, dimensions=(320, 24)).run()
                        if not res.clicked or not res.text:
                            return
                        pw = str(res.text)

                        con['password'] = self._enc(pw)
                        self.save_connections()

                else:
                    res = rumps.Window(message='Enter password:', cancel=True, dimensions=(320, 24)).run()
                    if not res.clicked or not res.text:
                        return
                    pw = str(res.text)

                env["SSHPASS"] = pw

                command += [f"-ossh_command={os.path.join(BIN_DIR, 'sshpass')} -eSSHPASS ssh"]

            if self._debug:
                print(' '.join(command))

            proc = subprocess.Popen(command, env=env)

            self._poll_data[con['name']] = {'mount_point': mount_point, 'menu_item': sender, 'counter': int(MAX_WAIT_CONNECT_SEC / POLL_PERIOD_SEC)}
            if not self._poll_timer.is_alive():
                self._poll_timer.start()

        else:
            subprocess.Popen(["/usr/sbin/diskutil", "umount", "force", mount_point])
            sender.state = 0

    ########################################
    #
    ########################################
    def check_mount(self, timer):
        for con_name in list(self._poll_data.keys()):
            data = self._poll_data[con_name]
            data['counter'] -= 1
            if os.path.ismount(data['mount_point']):
                data['menu_item'].state = 1
                subprocess.call(["open", data['mount_point']])
                del self._poll_data[con_name]
            else:
                data['counter'] -= 1
                if data['counter'] <= 0:
                    print(f"Failed to connect to {con_name}")
                    rumps.notification("Connection failed", "", f"Failed to connect to {con_name}", sound=False)
                    del self._poll_data[con_name]

        if not self._poll_data:
            self._poll_timer.stop()

    ########################################
    #
    ########################################
    def reload_connections(self, _):
        self.load_connections()
        self.create_menu()

    ########################################
    #
    ########################################
    def load_connections(self):
        self.connection_dict = {}
        try:
            with open(self.connections_json_file, 'r') as f:
                # connection_list = eval(f.read())
                connection_list = json.loads(f.read())
            connection_list = sorted(connection_list, key=lambda row: row['name'])
            for row in connection_list:
                self.connection_dict[row["name"]] = row
        except Exception as e:
            print(e)
            rumps.Window(title='Error in JSON file', message=str(e), dimensions=(320, 0)).run()

    ########################################
    #
    ########################################
    def save_connections(self):
        connection_list = list(self.connection_dict.values())
        try:
            with open(self.connections_json_file, 'w') as f:
                f.write(json.dumps(connection_list, indent=4))
        except Exception as e:
            print(e)

    ########################################
    #
    ########################################
    def update_connections(self, imported):

        # make names unique
        con_names = [con['name'] for con in self.connection_dict.values()]
        for con in imported:
            if con['name'] in con_names:
                i = 1
                while con['name'] + f' ({i})' in con_names:
                    i += 1
                con['name'] += f' ({i})'

        connection_list = sorted(list(self.connection_dict.values()) + imported, key=lambda row: row['name'])

        self.connection_dict = {}
        for row in connection_list:
            self.connection_dict[row["name"]] = row

        self.save_connections()
        self.create_menu()

    ########################################
    #
    ########################################
    def import_connections_filezilla(self, _):
        # Generally considered a bad idea, but whatever, to keep the app small we don't add a xml parser like expat,
        # but instead use RegEx. If the FileZilla XML is not 100% valid and in expected format, the import would fail anyway
        try:
            imported = []
            with open(FILEZILLA_XML_FILE, 'r') as f:
                xml = f.read().replace('\n', '')
            for row in re.findall(r"<Server>(.*?)</Server>", xml):
                data = {k.lower(): v for (k, v) in re.findall(r"<([^ >]*).*?>(.*?)</.*?>", str(row))}
                if data['protocol'] != '1':
                    continue

                con = {}
                for k in ('name', 'host', 'port', 'user'):
                    con[k] = data[k]

                if data['logontype'] == '1':
                    con['auth'] = 'password'
                elif data['logontype'] == '5':
                    con['auth'] = 'key'
                elif data['logontype'] == '3':
                    con['auth'] = 'ask_password'
                else:
                    continue

                if 'pass' in data:
                    con["password"] = self._enc(base64.b64decode(data['pass']))
                if 'keyfile' in data:
                    con['key_file'] = data['keyfile']

                if 'remotedir' in data:
                    parts = data['remotedir'].split(' ')
                    parts = [parts[i] for i in range(3, len(parts), 2)]
                    con['path'] = '/' + '/'.join(parts)
                else:
                    con['path'] = '/'

                imported.append(con)
            self.update_connections(imported)

        except Exception as e:
            print(e)
            rumps.Window(title='Import failed', message=str(e), dimensions=(320, 0)).run()

    ########################################
    # no passwords
    ########################################
    def import_connections_cyberduck(self, _):
        try:
            imported = []
            for fn in os.listdir(CYBERDUCK_BM_DIR):
                fn = os.path.join(CYBERDUCK_BM_DIR, fn)
                with open(fn, 'r') as f:
                    xml = f.read().replace('\n', '')
                xml = re.sub(r'<key>[\S ]*?</key>\s*?<dict>.*?</dict>', '', xml)

                data = {}
                last_key = None
                for row in re.findall(r"<(key|string)>(.*?)</(key|string)>", xml):
                    if row[0] == 'key':
                        last_key = row[1]
                    elif row[0] == 'string':
                        data[last_key] = row[1]
                if data['Protocol'] != 'sftp':
                    continue

                con = {
                    'name': data['Nickname'] if 'Nickname' in data else data['Hostname'],
                    'path': data['Path'] if 'Path' in data else '/',
                    'auth': 'ask_password',
                    'host': data['Hostname'],
                    'port': data['Port'],
                    'user': data['Username'],
                }

                if 'Private Key File' in data:
                    con['auth'] = 'key'
                    con['key_file'] = data['Private Key File']

                imported.append(con)
            self.update_connections(imported)

        except Exception as e:
            print(e)
            rumps.Window(title='Import failed', message=str(e), dimensions=(320, 0)).run()

    ########################################
    #
    ########################################
    def _enc(self, pw):
        if type(pw) == str:
            pw = pw.encode()
        # pad with random ASCII letter
        while True:
            c = chr(random.randint(32, 127)).encode()
            if c != pw[-1]:
                break
        if len(pw) < 32:
            pw += c * (32 - len(pw))
        else:
            pw += c
        return bytes(a ^ b for a, b in zip(pw, MASTER_KEY)).hex()

    ########################################
    #
    ########################################
    def _dec(self, pw):
        pw_dec = bytes(a ^ b for a, b in zip(bytes.fromhex(pw), MASTER_KEY)).decode()
        return pw_dec.rstrip(pw_dec[-1])


if __name__ == "__main__":
    sys.excepthook = traceback.print_exception
    MyApp().run()
