# coding: utf-8
from __future__ import unicode_literals

import uuid
import xml.etree.ElementTree as etree
import json

from .common import InfoExtractor
from ..compat import compat_str
from ..utils import (
    extract_attributes,
    xpath_with_ns,
    xpath_element,
    xpath_text,
    int_or_none,
    parse_duration,
    ExtractorError,
    determine_ext,
)


class ITVIE(InfoExtractor):
    _VALID_URL = r'https?://(?:www\.)?itv\.com/hub/[^/]+/(?P<id>[0-9a-zA-Z]+)'
    _TEST = {
        'url': 'http://www.itv.com/hub/mr-bean-animated-series/2a2936a0053',
        'info_dict': {
            'id': '2a2936a0053',
            'ext': 'flv',
            'title': 'Home Movie',
        },
        'params': {
            # rtmp download
            'skip_download': True,
        },
    }

    def _real_extract(self, url):
        video_id = self._match_id(url)
        webpage = self._download_webpage(url, video_id)
        params = extract_attributes(self._search_regex(
            r'(?s)(<[^>]+id="video"[^>]*>)', webpage, 'params'))

        ns_map = {
            'soapenv': 'http://schemas.xmlsoap.org/soap/envelope/',
            'tem': 'http://tempuri.org/',
            'itv': 'http://schemas.datacontract.org/2004/07/Itv.BB.Mercury.Common.Types',
            'com': 'http://schemas.itv.com/2009/05/Common',
        }
        for ns, full_ns in ns_map.items():
            etree.register_namespace(ns, full_ns)

        def _add_ns(name):
            return xpath_with_ns(name, ns_map)

        def _add_sub_element(element, name):
            return etree.SubElement(element, _add_ns(name))

        req_env = etree.Element(_add_ns('soapenv:Envelope'))
        _add_sub_element(req_env, 'soapenv:Header')
        body = _add_sub_element(req_env, 'soapenv:Body')
        get_playlist = _add_sub_element(body, ('tem:GetPlaylist'))
        request = _add_sub_element(get_playlist, 'tem:request')
        _add_sub_element(request, 'itv:ProductionId').text = params['data-video-id']
        _add_sub_element(request, 'itv:RequestGuid').text = compat_str(uuid.uuid4()).upper()
        vodcrid = _add_sub_element(request, 'itv:Vodcrid')
        _add_sub_element(vodcrid, 'com:Id')
        _add_sub_element(request, 'itv:Partition')
        user_info = _add_sub_element(get_playlist, 'tem:userInfo')
        _add_sub_element(user_info, 'itv:Broadcaster').text = 'Itv'
        _add_sub_element(user_info, 'itv:DM')
        _add_sub_element(user_info, 'itv:RevenueScienceValue')
        _add_sub_element(user_info, 'itv:SessionId')
        _add_sub_element(user_info, 'itv:SsoToken')
        _add_sub_element(user_info, 'itv:UserToken')
        site_info = _add_sub_element(get_playlist, 'tem:siteInfo')
        _add_sub_element(site_info, 'itv:AdvertisingRestriction').text = 'None'
        _add_sub_element(site_info, 'itv:AdvertisingSite').text = 'ITV'
        _add_sub_element(site_info, 'itv:AdvertisingType').text = 'Any'
        _add_sub_element(site_info, 'itv:Area').text = 'ITVPLAYER.VIDEO'
        _add_sub_element(site_info, 'itv:Category')
        _add_sub_element(site_info, 'itv:Platform').text = 'DotCom'
        _add_sub_element(site_info, 'itv:Site').text = 'ItvCom'
        device_info = _add_sub_element(get_playlist, 'tem:deviceInfo')
        _add_sub_element(device_info, 'itv:ScreenSize').text = 'Big'
        player_info = _add_sub_element(get_playlist, 'tem:playerInfo')
        _add_sub_element(player_info, 'itv:Version').text = '2'

        headers = self.geo_verification_headers()
        headers.update({
            'Content-Type': 'text/xml; charset=utf-8',
            'SOAPAction': 'http://tempuri.org/PlaylistService/GetPlaylist',
        })
        resp_env = self._download_xml(
            params['data-playlist-url'], video_id,
            headers=headers, data=etree.tostring(req_env))
        playlist = xpath_element(resp_env, './/Playlist')
        if playlist is None:
            fault_string = xpath_text(resp_env, './/faultstring')
            raise ExtractorError('%s said: %s' % (self.IE_NAME, fault_string))
        title = xpath_text(playlist, 'EpisodeTitle', fatal=True)
        video_element = xpath_element(playlist, 'VideoEntries/Video', fatal=True)
        media_files = xpath_element(video_element, 'MediaFiles', fatal=True)
        rtmp_url = media_files.attrib['base']

        formats = []
        for media_file in media_files.findall('MediaFile'):
            play_path = xpath_text(media_file, 'URL')
            if not play_path:
                continue
            tbr = int_or_none(media_file.get('bitrate'), 1000)
            formats.append({
                'format_id': 'rtmp' + ('-%d' % tbr if tbr else ''),
                'url': rtmp_url,
                'play_path': play_path,
                'tbr': tbr,
                'ext': 'flv',
            })

        ios_playlist_url = params.get('data-video-playlist')
        hmac = params.get('data-video-hmac')
        if ios_playlist_url and hmac:
            headers = self.geo_verification_headers()
            headers.update({
                'Accept': 'application/vnd.itv.vod.playlist.v2+json',
                'Content-Type': 'application/json',
                'hmac': hmac.upper(),
            })
            ios_playlist = self._download_json(
                ios_playlist_url, video_id, data=json.dumps({
                    'user': {
                        'itvUserId': '',
                        'entitlements': [],
                        'token': ''
                    },
                    'device': {
                        'manufacturer': 'Apple',
                        'model': 'iPad',
                        'os': {
                            'name': 'iPhone OS',
                            'version': '9.3',
                            'type': 'ios'
                        }
                    },
                    'client': {
                        'version': '4.1',
                        'id': 'browser'
                    },
                    'variantAvailability': {
                        'featureset': {
                            'min': ['hls', 'aes'],
                            'max': ['hls', 'aes']
                        },
                        'platformTag': 'mobile'
                    }
                }).encode(), headers=headers, fatal=False)
            if ios_playlist:
                video_data = ios_playlist.get('Playlist', {}).get('Video', {})
                ios_base_url = video_data.get('Base')
                for media_file in video_data.get('MediaFiles', []):
                    href = media_file.get('Href')
                    if not href:
                        continue
                    if ios_base_url:
                        href = ios_base_url + href
                    ext = determine_ext(href)
                    if ext == 'm3u8':
                        formats.extend(self._extract_m3u8_formats(href, video_id, 'mp4', m3u8_id='hls', fatal=False))
                    else:
                        formats.append({
                            'url': href,
                        })
        self._sort_formats(formats)

        subtitles = {}
        for caption_url in video_element.findall('ClosedCaptioningURIs/URL'):
            if not caption_url.text:
                continue
            ext = determine_ext(caption_url.text, 'ttml')
            subtitles.setdefault('en', []).append({
                'url': caption_url.text,
                'ext': 'ttml' if ext == 'xml' else ext,
            })

        return {
            'id': video_id,
            'title': title,
            'formats': formats,
            'subtitles': subtitles,
            'episode_title': title,
            'episode_number': int_or_none(xpath_text(playlist, 'EpisodeNumber')),
            'series': xpath_text(playlist, 'ProgrammeTitle'),
            'duartion': parse_duration(xpath_text(playlist, 'Duration')),
        }
