#    This file is part of Lurklib.
#    Copyright (C) 2010  Jamie Shaw (LK-)
#
#    Lurklib is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    Lurklib is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with Lurklib.  If not, see <http://www.gnu.org/licenses/>.

""" Main Lurklib file. """

from __future__ import with_statement
from . import variables, exceptions, channel
from . import connection, optional, sending, squeries, uqueries

__version__ = '0.6.0.2'


class IRC(variables._Variables, exceptions._Exceptions,
           connection._Connection, channel._Channel,
           sending._Sending, uqueries._UserQueries,
           squeries._ServerQueries, optional._Optional):
    """ Core IRC-interaction class. """
    def __init__(self, server, hooks={}, port=None, nick='Lurklib',
                  user='Lurklib',
                  real_name='The Lurk Internet Relay Chat Library',
                  password=None, tls=False, encoding='UTF-8',
                  hide_called_events=True, ctcps=None, UTC=False):
        """
        Initializes Lurklib and connects to the IRC server.
        Required arguments:
        * server - IRC server to connect to.
        Optional arguments:
        * hooks - Event handles.
        * port=None - IRC port to use.
            if tls is selected it defaults to 6697 -
            if not, it defaults to 6667.
        * nick='Lurklib' - IRC nick to use.
            If a tuple/list is specified it will try to use the first,
            and if the first is already -
            used it will try to use the second and so on.
        * user='Lurklib' - IRC username to use.
        * real_name='The Lurk Internet Relay Chat Library'
             - IRC real name to use.
        * password=None - IRC server password.
        * tls=False - Should the connection use TLS/SSL?
        * encoding='UTF-8' - The encoding that should be used.
            if the IRC server specifies a CHARSET it will be used instead,
            however in the event of a LookupError it will fallback to this.
        * hide_calles_events=True
             - Whether or not to hide events that are -
             generated by calling a Lurklib channel method.
        * ctcps=None - CTCP response table.
            Responds to TIME, PING, SOURCE and VERSION by default.
        * UTC=False - Should Lurklib's time objects use UTC?
        """
        self.hooks = hooks
        self.hide_called_events = hide_called_events
        self.UTC = UTC
        self.fallback_encoding = encoding
        self.encoding = encoding
        self._clrf = '\r\n'

        if self.m_sys.version_info[0] == 2 and self.m_sys.version_info[1] < 6:
            self.tls = False
        else:
            self.tls = tls

        if ctcps == None:
            self.ctcps = { \
             'VERSION': 'Lurklib : %s' \
              % __version__,
             'SOURCE': 'http://github.com/LK-/Lurklib/',
             'PING': 1,
             'TIME': self.m_time.asctime,
             }
        else:
            self.ctcps = ctcps

        if server != None:
            self._init(server, nick, user, real_name, password, port, tls)

    def find(self, haystack, needle):
        """
        Finds needle in haystack.
        If needle is found return True, if not return False.
        Required arguments:
        * haystack - Text to search in.
        * needle - Text to search for.
        """
        qstatus = haystack.find(needle)
        if qstatus == -1:
            return False
        elif qstatus != -1:
            return True

    def send(self, msg):
        """ Send raw data with the clrf appended to it. """
        with self.lock:
            msg = msg.replace('\r', '\\r').replace('\n', '\\n') + self._clrf
            if self.m_sys.version_info[0] > 2:
                try:
                    data = bytes(msg, self.encoding)
                except LookupError:
                    data = bytes(msg, self.fallback_encoding)
            else:
                try:
                    data = msg.encode(self.encoding)
                except UnicodeDecodeError:
                    data = msg.encode(self.fallback_encoding)
            self.socket.send(data)

    def mcon(self):
        """ Buffer IRC data and handle PING/PONG. """
        with self.lock:
            sdata = ' '
            while sdata[-1] != self._clrf[-1]:
                if sdata == ' ':
                    sdata = ''
                if self.m_sys.version_info[0] > 2:
                    try:
                        sdata = sdata + self.socket.recv(4096).decode(self.encoding)
                    except LookupError:
                        sdata = sdata + self.socket.recv(4096).decode \
                            (self.fallback_encoding)
                else:
                    sdata = sdata + self.socket.recv(4096)

            lines = sdata.split(self._clrf)
            for line in lines:
                if line.find('PING :') == 0:
                    self.send(line.replace('PING', 'PONG'))
                if line != '':
                    self.buffer.append(line)

    def _recv(self):
        """ Return the next available IRC message in the buffer. """
        with self.lock:
            if self.index >= len(self.buffer):
                self.mcon()
            if self.index >= 199:
                self._resetbuffer()
                self.mcon()
            msg = self.buffer[self.index]
            while self.find(msg, 'PING :'):
                self.index += 1
                try:
                    msg = self.buffer[self.index]
                except IndexError:
                    self.mcon()
                    self.index -= 1

            self.index += 1
            return msg

    def readable(self, timeout=1):
        """
        Checks whether self._recv() will block or not.
        Optional arguments:
        * timeout=1 - How long to wait before returning False.
        """
        with self.lock:
            if len(self.buffer) > self.index:
                return True
            else:
                if self.m_select.select([self.socket], [], [], timeout)[0] == []:
                    return False
                else:
                    return True

    def _resetbuffer(self):
        """ Resets the IRC buffer. """
        with self.lock:
            self.index, self.buffer = 0, []

    def __close__(self):
        """ For use with the Python 'with' statement. """
        with self.lock:
            self.quit()

    def _from_(self, who):
        """
        Processes nick!user@host data.
        Returns a tuple containing, the nick, user and host.
        If a valid hostmask isn't found, return the data as is.
        Required arguments:
        * who - nick!user@host data.
        """
        try:
            host = who.split('@', 1)
            nickident = host[0].split('!', 1)
            nick = nickident[0]
            ident = nickident[1]
            host = host[1]
            return nick, ident, host
        except IndexError:
            return who

    def recv(self):
        """
        Parses an IRC protocol message.
        Required arguments:
        * msg - IRC message.
        """
        msg = self._recv().split(None, 3)
        if msg[1] in self.error_dictionary:
            self.exception(msg[1])
        return msg

    def stream(self, timeout=1000):
        """
        High-level IRC buffering system and processor.
        Optional arguments:
        * timeout=1000 - Time to wait before returning None.
            Defaults to waiting forever.
        """
        with self.lock:
            if timeout != 1000:
                if self.readable(timeout) == False:
                    return None
            data = self._recv()
            segments = data.split()

            if segments[1] == 'JOIN':
                who = self._from_(segments[0][1:])
                channel = segments[2][1:]
                if channel not in self.channels:
                    self.index -= 1
                    return 'JOIN', self.join(channel)
                else:
                    self.channels[channel]['USERS'][who[0]] = \
                    ['', '', '', '', '']
                return 'JOIN', who, channel

            elif segments[1] == 'PART':
                who = self._from_(segments[0].replace(':', '', 1))
                channel = segments[2]
                del self.channels[channel]['USERS'][who[0]]
                try:
                    reason = ' '.join(segments[3:]).replace(':', '', 1)
                    return 'PART', who, channel, reason
                except IndexError:
                    who = self._from_(segments[0].replace(':', '', 1))
                    return 'PART', who, channel, ''

            elif segments[1] == 'PRIVMSG':
                who = self._from_(segments[0].replace(':', '', 1))
                msg = ' '.join(segments[3:]).replace(':', '', 1)
                rvalue = 'PRIVMSG', (who, segments[2], msg)

                if msg.find('\001') == 0:
                    rctcp = self.ctcp_decode(msg).upper()
                    segments = rctcp.split()
                    if segments[0] == 'ACTION':
                        action = ' '.join(rctcp.split()[1:])
                        return 'ACTION', (rvalue[1][:2], action)
                    for ctcp in self.ctcps.keys():
                        if ctcp == segments[0] and self.ctcps[ctcp] != None:
                            if hasattr(self.ctcps[ctcp], '__call__'):
                                response = str(self.ctcps[ctcp]())
                            else:
                                try:
                                    response = segments[int(self.ctcps[ctcp])]
                                    response = '%s %s' % (ctcp, response)
                                except ValueError:
                                    response = self.ctcps[ctcp]
                            self.notice(who[0], self.ctcp_encode(response))
                            break
                    return 'CTCP', (rvalue[1][:2], rctcp)
                else:
                    return rvalue

            elif segments[1] == 'NOTICE':
                who = self._from_(segments[0].replace(':', '', 1))
                msg = ' '.join(segments[3:]).replace(':', '', 1)
                if msg.find('\001') == 0:
                    msg = self.ctcp_decode(msg)
                    return 'CTCP_REPLY', (who, segments[2], msg)
                return 'NOTICE', (who, segments[2], msg)

            elif segments[1] == 'MODE':
                mode = ' '.join(segments[3:]).replace(':', '', 1)
                who = self._from_(segments[0][1:])
                target = segments[2]
                if target != self.current_nick:
                    self.parse_cmode_string(mode, target)
                    return 'MODE', (who, segments[2], mode)
                else:
                    return 'MODE', (mode.replace(':', '', 1))

            elif segments[1] == 'KICK':
                who = self._from_(segments[0].replace(':', '', 1))
                if self.current_nick == segments[3]:
                    del self.channels['USERS'][segments[2]]
                del self.channels[channel][segments[3]]
                reason = ' '.join(segments[4:]).replace(':', '', 1)
                return 'KICK', (who, segments[2], segments[3], reason)

            elif segments[1] == 'INVITE':
                who = self._from_(segments[0].replace(':', '', 1))
                channel = segments[3].replace(':', '', 1)
                return 'INVITE', (who, segments[2], channel)

            elif segments[1] == 'NICK':
                who = self._from_(segments[0].replace(':', '', 1))
                new_nick = ' '.join(segments[2:])
                if self.current_nick == who[0]:
                    self.current_nick = new_nick
                for channel in self.channels:
                    priv_level = self.channels[channel]['USERS'][who[0]]
                    del self.channels[channel]['USERS'][who[0]]
                    self.channels[channel]['USERS'][new_nick] = priv_level
                return 'NICK', (who, new_nick)

            elif segments[1] == 'TOPIC':
                who = self._from_(segments[0].replace(':', '', 1))
                channel = segments[2]
                topic = ' '.join(segments[3:]).replace(':', '', 1)
                self.channels[channel]['TOPIC'] = topic
                return 'TOPIC', (who, channel, topic)

            elif segments[1] == 'QUIT':
                who = self._from_(segments[0].replace(':', '', 1))
                msg = ' '.join(segments[2:]).replace(':', '', 1)
                return 'QUIT', (who, msg)

            elif segments[1] == '250':
                self.lusers['HIGHESTCONNECTIONS'] = segments[6]
                self.lusers['TOTALCONNECTIONS'] = segments[9][1:]
                return 'LUSERS', self.lusers

            elif segments[1] == '251':
                self.lusers['USERS'] = segments[5]
                self.lusers['INVISIBLE'] = segments[8]
                self.lusers['SERVERS'] = segments[11]
                return 'LUSERS', self.lusers

            elif segments[1] == '252':
                self.lusers['OPERATORS'] = segments[3]
                return 'LUSERS', self.lusers

            elif segments[1] == '253':
                self.lusers['UNKNOWN'] = segments[3]
                return 'LUSERS', self.lusers

            elif segments[1] == '254':
                self.lusers['CHANNELS'] = segments[3]
                return 'LUSERS', self.lusers

            elif segments[1] == '255':
                self.lusers['CLIENTS'] = segments[5]
                self.lusers['LSERVERS'] = segments[8]
                return 'LUSERS', self.lusers

            elif segments[1] == '265':
                self.lusers['LOCALUSERS'] = segments[6]
                self.lusers['LOCALMAX'] = segments[8]
                return 'LUSERS', self.lusers

            elif segments[1] == '266':
                self.lusers['GLOBALUSERS'] = segments[6]
                self.lusers['GLOBALMAX'] = segments[8]
                return 'LUSERS', self.lusers

            elif segments[0] == 'ERROR':
                self.quit()
                return 'ERROR', ' '.join(segments[1:]).replace(':', '', 1)
            else:
                return 'UNKNOWN', self._parse(data)

    def compare(self, first, second):
        """
        Case in-sensitive comparison of two strings.
        Required arguments:
        * first - The first string to compare.
        * second - The second string to compare.
        """
        if first.lower() == second.lower():
            return True
        else:
            return False

    def process_once(self, timeout=0.01):
        """
        Handles an event and calls it's handler
        Optional arguments:
        * timeout=0.01 - Wait for an event until the timeout is reached.
        """
        event = self.stream(timeout)
        if event != None:
            try:
                if event[0] in self.hooks:
                    self.hooks[event[0]](event=event[1])
                elif 'UNHANDLED' in self.hooks:
                    self.hooks['UNHANDLED'](event)
                else:
                    raise self.UnhandledEvent
                ('Unhandled Event: %s' % event[0])
            except KeyError:
                if 'UNHANDLED' in self.hooks.keys():
                    self.hooks['UNHANDLED'](event)
                else:
                    raise self.UnhandledEvent
                ('Unhandled Event: %s' % event[0])

    def mainloop(self):
        """
        Handles events and calls their handler for infinity.
        """
        while self.keep_going:
            with self.lock:
                if 'AUTO' in self.hooks and self.readable(2) == False:
                    self.hooks['AUTO']()
                    del self.hooks['AUTO']
                if self.keep_going == False:
                    break
                self.process_once()

    def set_hook(self, trigger, method):
        """
        Sets a Lurklib hook.
        Required arguments:
        trigger - The event that will trigger the hook.
        method - The function that is to be called when said hook is triggered.
        """
        with self.lock:
            self.hooks[trigger] = method

    def remove_hook(self, trigger):
        """
        Removes a Lurklib hook.
        Required arguments:
        trigger - The event to no longer be handled
        """
        with self.lock:
            del self.hooks[trigger]

    def ctcp_encode(self, msg):
        """
        CTCP encodes a message.
        Required arguments:
        msg - The message to be CTCP encoded.
        Returns the encoded version of the message.
        """
        return '\001%s\001' % msg

    def ctcp_decode(self, msg):
        """
        Decodes a CTCP message.
        Required arguments:
        msg - The message to be decoded.
        Returns the decoded version of the message.
        """
        return msg.replace('\001', '')
