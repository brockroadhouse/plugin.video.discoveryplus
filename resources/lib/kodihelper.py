# -*- coding: utf-8 -*-

import os
import re
import sys
import json

from .dplay import Dplay

import xbmc
import xbmcvfs
import xbmcgui
import xbmcplugin
from xbmcaddon import Addon
import inputstreamhelper
from base64 import b64encode

try:  # Python 3
    from urllib.parse import urlencode
except ImportError:  # Python 2
    from urllib import urlencode


class KodiHelper(object):
    def __init__(self, base_url=None, handle=None):
        addon = self.get_addon()
        self.base_url = base_url
        self.handle = handle
        self.addon_path = xbmcvfs.translatePath(addon.getAddonInfo('path'))
        self.addon_profile = xbmcvfs.translatePath(addon.getAddonInfo('profile'))
        self.addon_name = addon.getAddonInfo('id')
        self.addon_version = addon.getAddonInfo('version')
        self.language = addon.getLocalizedString
        self.logging_prefix = '[%s-%s]' % (self.addon_name, self.addon_version)
        if not xbmcvfs.exists(self.addon_profile):
            xbmcvfs.mkdir(self.addon_profile)
        self.d = Dplay(self.addon_profile, self.get_setting('country'), self.logging_prefix,
                       self.get_setting('numresults'), self.get_setting('cookiestxt'),
                       self.get_setting('cookiestxt_file'), self.get_setting('cookie'), self.get_setting('us_uhd'))

    def get_addon(self):
        """Returns a fresh addon instance."""
        return Addon()

    def get_setting(self, setting_id):
        addon = self.get_addon()
        setting = addon.getSetting(setting_id)
        if setting == 'true':
            return True
        elif setting == 'false':
            return False
        else:
            return setting

    def get_kodi_version(self):
        version = xbmc.getInfoLabel('System.BuildVersion')
        return version.split('.')[0]

    def set_setting(self, key, value):
        return self.get_addon().setSetting(key, value)

    def log(self, string):
        msg = '%s: %s' % (self.logging_prefix, string)
        xbmc.log(msg=msg, level=xbmc.LOGDEBUG)

    def dialog(self, dialog_type, heading, message=None, options=None, nolabel=None, yeslabel=None):
        dialog = xbmcgui.Dialog()
        if dialog_type == 'ok':
            dialog.ok(heading, message)
        elif dialog_type == 'yesno':
            return dialog.yesno(heading, message, nolabel=nolabel, yeslabel=yeslabel)
        elif dialog_type == 'select':
            ret = dialog.select(heading, options)
            if ret > -1:
                return ret
            else:
                return None
        elif dialog_type == 'numeric':
            ret = dialog.numeric(0, heading, '', 1)
            if ret:
                return ret
            else:
                return None

    def get_user_input(self, heading, hidden=False):
        keyboard = xbmc.Keyboard('', heading, hidden)
        keyboard.doModal()
        if keyboard.isConfirmed():
            query = keyboard.getText()
            self.log('User input string: %s' % query)
        else:
            query = None

        if query and len(query) > 0:
            return query
        else:
            return None

    def check_for_credentials(self):
        self.d.get_token()  # Get new token before checking credentials
        if self.d.get_user_data()['attributes']['anonymous'] == True:
            raise self.d.DplayError(self.language(30022))
        return True

    def set_country(self):
        # Only set current country if it isn't already set
        if self.get_setting('country') == '':
            return self.set_setting('country', self.d.get_country())

    def reset_settings(self):
        self.set_setting('country', '')
        self.set_setting('numresults', '100')
        self.set_setting('cookiestxt', 'true')
        self.set_setting('cookiestxt_file', '')
        self.set_setting('cookie', '')
        self.set_setting('sync_playback', 'true')
        self.set_setting('us_uhd', 'false')
        self.set_setting('use_isa', 'true')
        self.set_setting('seasonsonly', 'false')
        self.set_setting('flattentvshows', 'false')
        self.set_setting('iptv.enabled', 'false')

        # Remove cookies file
        cookie_file = os.path.join(self.addon_profile, 'cookie_file')
        if os.path.exists(cookie_file):
            os.remove(cookie_file)

    def add_item(self, title, params, items=False, folder=True, playable=False, info=None, art=None, content=False,
                 menu=None, resume=None, total=None, folder_name=None, sort_method=None):
        addon = self.get_addon()
        listitem = xbmcgui.ListItem(label=title, offscreen=True)

        if playable:
            listitem.setProperty('IsPlayable', 'true')
            listitem.setProperty('get_stream_details_from_player', 'true')
            folder = False
        if resume:
            listitem.setProperty("ResumeTime", str(resume))
            listitem.setProperty("TotalTime", str(total))
        if art:
            listitem.setArt(art)
        else:
            art = {
                'icon': addon.getAddonInfo('icon'),
                'fanart': addon.getAddonInfo('fanart')
            }
            listitem.setArt(art)
        if info:
            listitem.setInfo('video', info)
        if content:
            xbmcplugin.setContent(self.handle, content)
        if menu:
            listitem.addContextMenuItems(menu)
        if folder_name:
            xbmcplugin.setPluginCategory(self.handle, folder_name)
        if sort_method:
            if sort_method == 'unsorted':
                xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_UNSORTED)
                xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_LABEL)
            if sort_method == 'sort_label':
                xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_LABEL)
            if sort_method == 'sort_episodes':
                xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_EPISODE)
                xbmcplugin.addSortMethod(self.handle, xbmcplugin.SORT_METHOD_VIDEO_TITLE)
            if sort_method == 'bottom':
                listitem.setProperty("SpecialSort", "bottom")

        recursive_url = self.base_url + '?' + urlencode(params)

        if items is False:
            xbmcplugin.addDirectoryItem(self.handle, recursive_url, listitem, folder)
        else:
            items.append((recursive_url, listitem, folder))
            return items

    def eod(self):
        """Tell Kodi that the end of the directory listing is reached."""
        xbmcplugin.endOfDirectory(self.handle)

    def refresh_list(self):
        """Refresh listing after adding or deleting favorites"""
        return xbmc.executebuiltin('Container.Refresh')

    # Up Next integration
    def upnext_signal(self, sender, next_info):
        """Send a signal to Kodi using JSON RPC"""
        self.log("Sending Up Next data: %s" % next_info)
        data = [self.to_unicode(b64encode(json.dumps(next_info).encode()))]
        self.notify(sender=sender + '.SIGNAL', message='upnext_data', data=data)

    def notify(self, sender, message, data):
        """Send a notification to Kodi using JSON RPC"""
        result = self.jsonrpc(method='JSONRPC.NotifyAll', params=dict(
            sender=sender,
            message=message,
            data=data,
        ))
        if result.get('result') != 'OK':
            self.log('Failed to send notification: %s' % result.get('error').get('message'))
            return False
        self.log('Succesfully sent notification')
        return True

    def jsonrpc(self, **kwargs):
        """ Perform JSONRPC calls """
        if kwargs.get('id') is None:
            kwargs.update(id=0)
        if kwargs.get('jsonrpc') is None:
            kwargs.update(jsonrpc='2.0')

        self.log("Sending notification event data: %s" % kwargs)
        return json.loads(xbmc.executeJSONRPC(json.dumps(kwargs)))

    def to_unicode(self, text, encoding='utf-8', errors='strict'):
        """Force text to unicode"""
        if isinstance(text, bytes):
            return text.decode(encoding, errors=errors)
        return text

    # End of Up next integration

    def play_item(self, video_id, video_type):
        useIsa = self.get_setting('use_isa')
        try:
            stream = self.d.get_stream(video_id, video_type)
            playitem = xbmcgui.ListItem(path=stream['url'], offscreen=True)

            # at least d+ India has dash streams that are not drm protected
            # website uses hls stream for those videos but we are using first stream in PlaybackInfo and that can be dash
            # this is tested to work
            if stream['type'] == 'dash':
                # Kodi 19 Matrix or higher
                if self.get_kodi_version() >= '19':
                    playitem.setProperty('inputstream', 'inputstream.adaptive')
                # Kodi 18 Leia
                else:
                    playitem.setProperty('inputstreamaddon', 'inputstream.adaptive')

                playitem.setProperty('inputstream.adaptive.manifest_type', 'mpd')

                # DRM enabled = use Widevine
                if stream['drm_enabled']:
                    is_helper = inputstreamhelper.Helper('mpd', drm='com.widevine.alpha')
                    if is_helper.check_inputstream():
                        playitem.setProperty('inputstream.adaptive.license_type', 'com.widevine.alpha')
                        if stream['drm_token']:
                            header = 'PreAuthorization=' + stream['drm_token']
                            playitem.setProperty('inputstream.adaptive.license_key',
                                                stream['license_url'] + '|' + header + '|R{SSM}|')
                        else:
                            playitem.setProperty('inputstream.adaptive.license_key', stream['license_url'] + '||R{SSM}|')
            else:

                if useIsa:
                    # Kodi 19 Matrix or higher
                    if self.get_kodi_version() >= '19':
                        playitem.setProperty('inputstream', 'inputstream.adaptive')
                    # Kodi 18 Leia
                    else:
                        playitem.setProperty('inputstreamaddon', 'inputstream.adaptive')

                    playitem.setProperty('inputstream.adaptive.manifest_type', 'hls')

            # Get metadata to use for Up next only in episodes and clips (can also be aired sport events)
            if video_type == 'EPISODE' or video_type == 'CLIP':
                # Get current episode info
                current_episode = self.d.get_current_episode_info(video_id=video_id)

                images = list(filter(lambda x: x['type'] == 'image', current_episode['included']))
                shows = list(filter(lambda x: x['type'] == 'show', current_episode['included']))

                show_fanart_image = None
                show_logo_image = None
                show_poster_image = None
                for show in shows:
                    if show['id'] == current_episode['data']['relationships']['show']['data']['id']:
                        show_title = show['attributes']['name']

                        if show['relationships'].get('images'):
                            for image in images:
                                for show_images in show['relationships']['images']['data']:
                                    if image['id'] == show_images['id']:
                                        if image['attributes']['kind'] == 'default':
                                            show_fanart_image = image['attributes']['src']
                                        if image['attributes']['kind'] == 'logo':
                                            show_logo_image = image['attributes']['src']
                                        if image['attributes']['kind'] == 'poster_with_logo':
                                            show_poster_image = image['attributes']['src']

                if current_episode['data']['relationships'].get('images'):
                    for i in images:
                        if i['id'] == current_episode['data']['relationships']['images']['data'][0]['id']:
                            video_thumb_image = i['attributes']['src']
                else:
                    video_thumb_image = None

                duration = current_episode['data']['attributes']['videoDuration'] / 1000.0 if current_episode['data'][
                    'attributes'].get('videoDuration') else None

                info = {
                    'mediatype': 'episode',
                    'title': current_episode['data']['attributes'].get('name').lstrip(),
                    'tvshowtitle': show_title,
                    'season': current_episode['data']['attributes'].get('seasonNumber'),
                    'episode': current_episode['data']['attributes'].get('episodeNumber'),
                    'plot': current_episode['data']['attributes'].get('description'),
                    'duration': duration,
                    'aired': current_episode['data']['attributes'].get('airDate')
                }

                playitem.setInfo('video', info)

                art = {
                    'fanart': show_fanart_image,
                    'thumb': video_thumb_image,
                    'clearlogo': show_logo_image,
                    'poster': show_poster_image
                }

                playitem.setArt(art)

                player = DplusPlayer()
                player.resolve(playitem)

                player.video_id = video_id
                player.current_show_id = current_episode['data']['relationships']['show']['data']['id']
                player.current_episode_info = info
                player.current_episode_art = art

                monitor = xbmc.Monitor()
                while not monitor.abortRequested() and player.playing:
                    if player.isPlayingVideo():
                        player.video_totaltime = player.getTotalTime()
                        player.video_lastpos = player.getTime()

                    xbmc.sleep(1000)

            # Live TV
            else:
                xbmcplugin.setResolvedUrl(self.handle, True, listitem=playitem)

        except self.d.DplayError as error:
            self.dialog('ok', self.language(30006), error.value)

class DplusPlayer(xbmc.Player):
    def __init__(self):
        base_url = sys.argv[0]
        handle = int(sys.argv[1])
        self.helper = KodiHelper(base_url, handle)
        self.video_id = None
        self.current_show_id = None
        self.current_episode_info = ''
        self.current_episode_art = ''
        self.video_lastpos = 0
        self.video_totaltime = 0
        self.playing = False
        self.paused = False

    def resolve(self, li):
        xbmcplugin.setResolvedUrl(self.helper.handle, True, listitem=li)
        self.playing = True

    def onPlayBackStarted(self):  # pylint: disable=invalid-name
        """Called when user starts playing a file"""
        self.helper.log('[DplusPlayer] Event onPlayBackStarted')

        self.onAVStarted()

    def onAVStarted(self):  # pylint: disable=invalid-name
        """Called when Kodi has a video or audiostream"""
        self.helper.log('[DplusPlayer] Event onAVStarted')
        self.push_upnext()

    def onPlayBackSeek(self, time, seekOffset):  # pylint: disable=invalid-name
        """Called when user seeks to a time"""
        self.helper.log('[DplusPlayer] Event onPlayBackSeek time=' + str(time) + ' offset=' + str(seekOffset))
        self.video_lastpos = time // 1000

        # If we seek beyond the end, exit Player
        if self.video_lastpos >= self.video_totaltime:
            self.stop()

    def onPlayBackPaused(self):  # pylint: disable=invalid-name
        """Called when user pauses a playing file"""
        self.helper.log('[DplusPlayer] Event onPlayBackPaused')
        self.update_playback_progress()
        self.paused = True

    def onPlayBackEnded(self):  # pylint: disable=invalid-name
        """Called when Kodi has ended playing a file"""
        self.helper.log('[DplusPlayer] Event onPlayBackEnded')
        self.update_playback_progress()
        self.playing = False
        # Up Next calls onPlayBackEnded before onPlayBackStarted if user doesn't select Watch Now
        # Reset current video id
        self.video_id = None

    def onPlayBackStopped(self):  # pylint: disable=invalid-name
        """Called when user stops Kodi playing a file"""
        self.helper.log('[DplusPlayer] Event onPlayBackStopped')
        self.update_playback_progress()
        self.playing = False
        # Reset current video id
        self.video_id = None

    def onPlayerExit(self):  # pylint: disable=invalid-name
        """Called when player exits"""
        self.helper.log('[DplusPlayer] Event onPlayerExit')
        self.update_playback_progress()
        self.playing = False

    def onPlayBackResumed(self):  # pylint: disable=invalid-name
        """Called when user resumes a paused file or a next playlist item is started"""
        if self.paused:
            suffix = 'after pausing'
            self.paused = False
        # playlist change
        # Up Next uses this when user clicks Watch Now, only happens if user is watching first episode in row after
        # that onPlayBackEnded is used even if user clicks Watch Now
        else:
            suffix = 'after playlist change'
            self.paused = False
            self.update_playback_progress()
            # Reset current video id
            self.video_id = None
        log = '[DplusPlayer] Event onPlayBackResumed ' + suffix
        self.helper.log(log)

    def push_upnext(self):
        if not self.video_id:
            return
        self.helper.log('Getting next episode info')
        next_episode = self.helper.d.get_next_episode_info(current_video_id=self.video_id)

        if next_episode.get('data'):
            self.helper.log('Current episode name: %s' % self.current_episode_info['title'].encode('utf-8'))
            self.helper.log(
                'Next episode name: %s' % next_episode['data'][0]['attributes'].get('name').encode(
                    'utf-8').lstrip())

            images = list(filter(lambda x: x['type'] == 'image', next_episode['included']))
            shows = list(filter(lambda x: x['type'] == 'show', next_episode['included']))

            show_fanart_image = None
            show_logo_image = None
            show_poster_image = None
            for show in shows:
                if show['id'] == next_episode['data'][0]['relationships']['show']['data']['id']:
                    next_episode_show_title = show['attributes']['name']

                    if show['relationships'].get('images'):
                        for image in images:
                            for show_images in show['relationships']['images']['data']:
                                if image['id'] == show_images['id']:
                                    if image['attributes']['kind'] == 'default':
                                        show_fanart_image = image['attributes']['src']
                                    if image['attributes']['kind'] == 'logo':
                                        show_logo_image = image['attributes']['src']
                                    if image['attributes']['kind'] == 'poster_with_logo':
                                        show_poster_image = image['attributes']['src']

            if next_episode['data'][0]['relationships'].get('images'):
                for i in images:
                    if i['id'] == next_episode['data'][0]['relationships']['images']['data'][0]['id']:
                        next_episode_thumb_image = i['attributes']['src']
            else:
                next_episode_thumb_image = None

            if self.current_episode_info.get('aired'):
                current_episode_aired = self.helper.d.parse_datetime(self.current_episode_info['aired']).strftime(
                    '%d.%m.%Y')
            else:
                current_episode_aired = ''

            if next_episode['data'][0]['attributes'].get('airDate'):
                next_episode_aired = self.helper.d.parse_datetime(
                    next_episode['data'][0]['attributes']['airDate']).strftime('%d.%m.%Y')
            else:
                next_episode_aired = ''

            next_info = dict(
                current_episode=dict(
                    episodeid=self.video_id,
                    tvshowid=self.current_show_id,
                    title=self.current_episode_info['title'],
                    art={
                        'thumb': self.current_episode_art['thumb'],
                        'tvshow.clearart': '',
                        'tvshow.clearlogo': self.current_episode_art['clearlogo'],
                        'tvshow.fanart': self.current_episode_art['fanart'],
                        'tvshow.landscape': '',
                        'tvshow.poster': self.current_episode_art['poster'],
                    },
                    season=self.current_episode_info['season'],
                    episode=self.current_episode_info['episode'],
                    showtitle=self.current_episode_info['tvshowtitle'],
                    plot=self.current_episode_info['title'],
                    playcount='',
                    rating=None,
                    firstaired=current_episode_aired,
                    runtime=self.current_episode_info['duration'],
                ),
                next_episode=dict(
                    episodeid=next_episode['data'][0]['id'],
                    tvshowid=next_episode['data'][0]['relationships']['show']['data']['id'],
                    title=next_episode['data'][0]['attributes'].get('name').lstrip(),
                    art={
                        'thumb': next_episode_thumb_image,
                        'tvshow.clearart': '',
                        'tvshow.clearlogo': show_logo_image,
                        'tvshow.fanart': show_fanart_image,
                        'tvshow.landscape:': '',
                        'tvshow.poster': show_poster_image,
                    },
                    season=next_episode['data'][0]['attributes'].get('seasonNumber'),
                    episode=next_episode['data'][0]['attributes'].get('episodeNumber'),
                    showtitle=next_episode_show_title,
                    plot=next_episode['data'][0]['attributes'].get('description'),
                    playcount='',
                    rating=None,
                    firstaired=next_episode_aired,
                    runtime=next_episode['data'][0]['attributes'].get('videoDuration') / 1000.0,
                ),

                play_url='plugin://' + self.helper.addon_name + '/?action=play&video_id=' +
                         next_episode['data'][0]['id'] + '&video_type=' + next_episode['data'][0]['attributes'][
                             'videoType'],
                notification_time='',
            )

            self.helper.upnext_signal(sender=self.helper.addon_name, next_info=next_info)

        else:
            self.helper.log('No next episode available')

    def update_playback_progress(self):
        if not self.video_id:
            return
        if not self.helper.get_setting('sync_playback'):
            return
        video_lastpos = format(self.video_lastpos, '.0f')
        video_totaltime = format(self.video_totaltime, '.0f')
        video_percentage = self.video_lastpos * 100 / self.video_totaltime
        # Convert to milliseconds
        video_lastpos_msec = int(video_lastpos) * 1000
        video_totaltime_msec = int(video_totaltime) * 1000

        self.helper.log('Video totaltime msec: %s' % str(video_totaltime_msec))
        self.helper.log('Video lastpos msec: %s' % str(video_lastpos_msec))
        self.helper.log('Video percentage watched: %s' % str(video_percentage))

        # Get new token before updating playback progress
        self.helper.d.get_token()

        # Over 92 percent watched = use totaltime
        if video_percentage > 92:
            self.helper.log('Marking episode completely watched')
            # discovery+ wants POST before PUT
            self.helper.d.update_playback_progress('post', self.video_id, video_totaltime_msec)
            self.helper.d.update_playback_progress('put', self.video_id, video_totaltime_msec)
        else:
            self.helper.log('Marking episode partly watched')
            # discovery+ wants POST before PUT
            self.helper.d.update_playback_progress('post', self.video_id, video_lastpos_msec)
            self.helper.d.update_playback_progress('put', self.video_id, video_lastpos_msec)
