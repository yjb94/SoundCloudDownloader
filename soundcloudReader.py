#! /usr/bin/env python
from __future__ import unicode_literals

import argparse
import demjson
import re
import requests
import soundcloud
import sys

from clint.textui import colored, puts, progress
from datetime import datetime
from mutagen.mp3 import MP3, EasyMP3
from mutagen.id3 import APIC
from mutagen.id3 import ID3 as OldID3
from subprocess import Popen, PIPE
from os.path import exists, join
from os import mkdir

####################################################################

# Please be nice with this!
CLIENT_ID = '175c043157ffae2c6d5fed16c3d95a4c'
CLIENT_SECRET = '99a51990bd81b6a82c901d4cc6828e46'
MAGIC_CLIENT_ID = 'b45b1aa10f1ac2941910a7f0d10f8e28'

AGGRESSIVE_CLIENT_ID = '02gUJC0hH2ct1EGOcYXQIzRFU91c72Ea'
APP_VERSION = '1464790339'


####################################################################


def main():
    """
    Main function.

    Converts arguments to Python and processes accordingly.

    """
    parser = argparse.ArgumentParser(description='SoundScrape. Scrape an artist from SoundCloud.\n')
    parser.add_argument('artist_url', metavar='U', type=str,
                        help='An artist\'s SoundCloud username or URL')
    parser.add_argument('-n', '--num-tracks', type=int, default=sys.maxsize,
                        help='The number of tracks to download')
    parser.add_argument('-g', '--group', action='store_true',
                        help='Use if downloading tracks from a SoundCloud group')
    parser.add_argument('-l', '--likes', action='store_true',
                        help='Download all of a user\'s Likes.')
    parser.add_argument('-d', '--downloadable', action='store_true',
                        help='Only fetch traks with a Downloadable link.')
    parser.add_argument('-t', '--track', type=str, default='',
                        help='The name of a specific track by an artist')
    parser.add_argument('-f', '--folders', action='store_true',
                        help='Organize saved songs in folders by artists')
    parser.add_argument('-o', '--open', action='store_true',
                        help='Open downloaded files after downloading.')
    parser.add_argument('-k', '--keep', action='store_true',
                        help='Keep 30-second preview tracks')

    args = parser.parse_args()
    vargs = vars(args)
    if not any(vargs.values()):
        parser.error('Please supply an artist\'s username or URL!')

    artist_url = vargs['artist_url']

    get_soundcloud(vargs)


####################################################################
# SoundCloud
####################################################################


def get_soundcloud(vargs):
    """
    Main SoundCloud path.
    """
    artist_url = vargs['artist_url']
    track_permalink = vargs['track']
    keep_previews = vargs['keep']
    folders = vargs['folders']

    id3_extras = {}
    one_track = False
    likes = False
    client = get_client()
    if 'soundcloud' not in artist_url.lower():
        if vargs['group']:
            artist_url = 'https://soundcloud.com/groups/' + artist_url.lower()
        elif len(track_permalink) > 0:
            one_track = True
            track_url = 'https://soundcloud.com/' + artist_url.lower() + '/' + track_permalink.lower()
        else:
            artist_url = 'https://soundcloud.com/' + artist_url.lower()
            if vargs['likes'] or 'likes' in artist_url.lower():
                likes = True
    if 'likes' in artist_url.lower():
        artist_url = artist_url[0:artist_url.find('/likes')]

    if one_track:
        num_tracks = 1
    else:
        num_tracks = vargs['num_tracks']

    try:
        if one_track:
            resolved = client.get('/resolve', url=track_url, limit=200)

        elif likes:
            userId = str(client.get('/resolve', url=artist_url).id)
            resolved = client.get('/users/' + userId + '/favorites', limit=200)
        else:
            resolved = client.get('/resolve', url=artist_url, limit=200)

    except Exception as e:  # HTTPError?

        # SoundScrape is trying to prevent us from downloading this.
        # We're going to have to stop trusting the API/client and 
        # do all our own scraping. Boo.

        message = str(e)
        item_id = message.rsplit('/', 1)[-1].split('.json')[0].split('?client_id')[0]
        hard_track_url = get_hard_track_url(item_id)

        track_data = get_soundcloud_data(artist_url)
        puts(colored.green("Scraping") + colored.white(": " + track_data['title']))

        filenames = []
        filename = sanitize_filename(track_data['artist'] + ' - ' + track_data['title'] + '.mp3')

        if folders:
            name = track_data['artist']
            if not exists(name):
                mkdir(name)
            filename = join(name, filename)

        if exists(filename) and folders:
            puts(colored.yellow("Track already downloaded: ") + colored.white(track_title))
            return None

        filename = download_file(hard_track_url, filename)
        tag_file(filename,
                 artist=track_data['artist'],
                 title=track_data['title'],
                 year='2016',
                 genre='',
                 album='',
                 artwork_url='')

        filenames.append(filename)

    else:
        aggressive = False

        # This is is likely a 'likes' page.
        if not hasattr(resolved, 'kind'):
            tracks = resolved
        else:
            if resolved.kind == 'artist':
                artist = resolved
                artist_id = str(artist.id)
                tracks = client.get('/users/' + artist_id + '/tracks', limit=200)
            elif resolved.kind == 'playlist':
                tracks = resolved.tracks
                id3_extras['album'] = resolved.title
            elif resolved.kind == 'track':
                tracks = [resolved]
            elif resolved.kind == 'group':
                group = resolved
                group_id = str(group.id)
                tracks = client.get('/groups/' + group_id + '/tracks', limit=200)
            else:
                artist = resolved
                artist_id = str(artist.id)
                tracks = client.get('/users/' + artist_id + '/tracks', limit=200)
                if tracks == [] and artist.track_count > 0:
                    aggressive = True
                    filenames = []

                    data = get_soundcloud_api2_data(artist_id)

                    def download_track(track, album_name=u''):
    
                        hard_track_url = get_hard_track_url(track['id'])

                        # We have no info on this track whatsoever.
                        if not 'title' in track:
                            return None

                        if not keep_previews:
                            if (track.get('duration', 0) < track.get('full_duration', 0)):
                                puts(colored.yellow("Skipping preview track") + colored.white(": " + track['title']))
                                return None

                        # May not have a "full name"
                        name = track['user']['full_name']
                        if name == '':
                            name = track['user']['username']

                        filename = sanitize_filename(name + ' - ' + track['title'] + '.mp3')

                        if folders:
                            if not exists(name):
                                mkdir(name)
                            filename = join(name, filename)

                        if exists(filename) and folders:
                            puts(colored.yellow("Track already downloaded: ") + colored.white(track_title))
                            return None

                        # Skip already downloaded track.
                        if filename in filenames:
                            return None

                        if hard_track_url:
                            puts(colored.green("Scraping") + colored.white(": " + track['title']))
                        else:
                            # Region coded?
                            puts(colored.yellow("Unable to download") + colored.white(": " + track['title']))
                            return None

                        filename = download_file(hard_track_url, filename)
                        tag_file(filename,
                                 artist=name,
                                 title=track['title'],
                                 year=track['created_at'][:4],
                                 genre=track['genre'],
                                 album=album_name,
                                 artwork_url=track['artwork_url'])

                        return filename

                    for track in data['collection']:

                        if len(filenames) >= num_tracks:
                            break

                        if track['type'] == 'playlist':
                            for playlist_track in track['playlist']['tracks']:
                                album_name = track['playlist']['title']
                                filename = download_track(playlist_track, album_name)
                                if filename:
                                    filenames.append(filename)
                        else:
                            d_track = track['track']
                            filename = download_track(d_track)
                            if filename:
                                filenames.append(filename)

        if not aggressive:
            filenames = get_download_urls(client, tracks, num_tracks, vargs['downloadable'], vargs['folders'],
                                        id3_extras=id3_extras)

    # if vargs['open']:
    #     open_files(filenames)
    return filenames


def get_client():
    """
    Return a new SoundCloud Client object.
    """
    client = soundcloud.Client(client_id=CLIENT_ID)
    return client


def get_download_urls(client, tracks, num_tracks=sys.maxsize, downloadable=False, folders=False, id3_extras={}):
    """
    Given a list of tracks, iteratively download all of them.

    """

    filenames = []

    for i, track in enumerate(tracks):

        # "Track" and "Resource" objects are actually different,
        # even though they're the same.
        if isinstance(track, soundcloud.resource.Resource):

            try:

                t_track = {}
                t_track['downloadable'] = track.downloadable
                t_track['streamable'] = track.streamable
                t_track['title'] = track.title
                t_track['user'] = {'username': track.user['username']}
                t_track['release_year'] = track.release
                t_track['genre'] = track.genre
                t_track['artwork_url'] = track.artwork_url
                if track.downloadable:
                    t_track['stream_url'] = track.download_url
                else:
                    if downloadable:
                        puts(colored.red("Skipping") + colored.white(": " + track.title))
                        continue
                    if hasattr(track, 'stream_url'):
                        t_track['stream_url'] = track.stream_url
                    else:
                        t_track['direct'] = True
                        streams_url = "https://api.soundcloud.com/i1/tracks/%s/streams?client_id=%s&app_version=%s" % (
                        str(track.id), AGGRESSIVE_CLIENT_ID, APP_VERSION)
                        response = requests.get(streams_url).json()
                        t_track['stream_url'] = response['http_mp3_128_url']

                track = t_track
            except Exception as e:
                puts(colored.white(track.title) + colored.red(' is not downloadable.'))
                print(e)
                continue

        if i > num_tracks - 1:
            continue
        try:
            if not track.get('stream_url', False):
                puts(colored.white(track['title']) + colored.red(' is not downloadable.'))
                continue
            else:
                track_artist = sanitize_filename(track['user']['username'])
                track_title = sanitize_filename(track['title'])
                track_filename = track_artist + ' - ' + track_title + '.mp3'

                if folders:
                    if not exists(track_artist):
                        mkdir(track_artist)
                    track_filename = join(track_artist, track_filename)

                if exists(track_filename) and folders:
                    puts(colored.yellow("Track already downloaded: ") + colored.white(track_title))
                    continue

                #puts(colored.green("Downloading") + colored.white(": " + track['title']))
                if track.get('direct', False):
                    location = track['stream_url']
                else:
                    stream = client.get(track['stream_url'], allow_redirects=False, limit=200)
                    if hasattr(stream, 'location'):
                        location = stream.location
                    else:
                        location = stream.url
                #real soundcloud file url
                #puts("DownLoad URL : " + location)
                filenames.append(location)
                # path = download_file(location, track_filename)
                # tag_file(path,
                #          artist=track['user']['username'],
                #          title=track['title'],
                #          year=track['release_year'],
                #          genre=track['genre'],
                #          album=id3_extras.get('album', None),
                #          artwork_url=track['artwork_url'])
                # filenames.append(path)
        except Exception as e:
            puts(colored.red("Problem downloading ") + colored.white(track['title']))
            print(e)

    return filenames


def get_soundcloud_data(url):
    """
    Scrapes a SoundCloud page for a track's important information.

    Returns:
        dict: of audio data

    """

    data = {}

    request = requests.get(url)

    title_tag = request.text.split('<title>')[1].split('</title')[0]
    data['title'] = title_tag.split(' by ')[0].strip()
    data['artist'] = title_tag.split(' by ')[1].split('|')[0].strip()
    # XXX Do more..

    return data
def get_soundcloud_api2_data(artist_id):
    """
    Scrape the new API. Returns the parsed JSON response.
    """

    v2_url = "https://api-v2.soundcloud.com/stream/users/%s?limit=500&client_id=%s&app_version=%s" % (
    artist_id, AGGRESSIVE_CLIENT_ID, APP_VERSION)
    response = requests.get(v2_url)
    parsed = response.json()

    return parsed
def get_hard_track_url(item_id):
    """
    Hard-scrapes a track.
    """

    streams_url = "https://api.soundcloud.com/i1/tracks/%s/streams/?client_id=%s&app_version=%s" % (
    item_id, AGGRESSIVE_CLIENT_ID, APP_VERSION)
    response = requests.get(streams_url)
    json_response = response.json()

    if response.status_code == 200:
        hard_track_url = json_response['http_mp3_128_url']
        return hard_track_url
    else:
        return None

####################################################################
# File Utility
####################################################################


def download_file(url, path):
    """
    Download an individual file.
    """

    if url[0:2] == '//':
        url = 'https://' + url[2:]

    r = requests.get(url, stream=True)
    with open(path, 'wb') as f:
        total_length = int(r.headers.get('content-length', 0))
        for chunk in progress.bar(r.iter_content(chunk_size=1024), expected_size=(total_length / 1024) + 1):
            if chunk:  # filter out keep-alive new chunks
                f.write(chunk)
                f.flush()

    return path


def tag_file(filename, artist, title, year=None, genre=None, artwork_url=None, album=None, track_number=None):
    """
    Attempt to put ID3 tags on a file.

    Args:
        artist (str):
        title (str):
        year (int):
        genre (str):
        artwork_url (str):
        album (str):
        track_number (str):
        filename (str):
    """

    try:
        audio = EasyMP3(filename)
        audio.tags = None
        audio["artist"] = artist
        audio["title"] = title
        if year:
            audio["date"] = str(str(year).encode('ascii','ignore'))
        if album:
            audio["album"] = album
        if track_number:
            audio["tracknumber"] = track_number
        if genre:
            audio["genre"] = genre
        audio.save()

        if artwork_url:

            artwork_url = artwork_url.replace('https', 'http')

            mime = 'image/jpeg'
            if '.jpg' in artwork_url:
                mime = 'image/jpeg'
            if '.png' in artwork_url:
                mime = 'image/png'

            if '-large' in artwork_url:
                new_artwork_url = artwork_url.replace('-large', '-t500x500')
                try:
                    image_data = requests.get(new_artwork_url).content
                except Exception as e:
                    # No very large image available.
                    image_data = requests.get(artwork_url).content
            else:
                image_data = requests.get(artwork_url).content

            audio = MP3(filename, ID3=OldID3)
            audio.tags.add(
                APIC(
                    encoding=3,  # 3 is for utf-8
                    mime=mime,
                    type=3,  # 3 is for the cover image
                    desc='Cover',
                    data=image_data
                )
            )
            audio.save()
    except Exception as e:
        print(e)


def open_files(filenames):
    """
    Call the system 'open' command on a file.
    """
    command = ['open'] + filenames
    process = Popen(command, stdout=PIPE, stderr=PIPE)
    stdout, stderr = process.communicate()


def sanitize_filename(filename):
    """
    Make sure filenames are valid paths.

    Returns:
        str: 
    """
    sanitized_filename = re.sub(r'[/\\:*?"<>|]', '-', filename)
    sanitized_filename = sanitized_filename.replace('&', 'and')
    sanitized_filename = sanitized_filename.replace('"', '')
    sanitized_filename = sanitized_filename.replace("'", '')
    return sanitized_filename


####################################################################
# Main
####################################################################

if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(e)
