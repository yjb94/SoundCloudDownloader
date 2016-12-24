from soundcloudReader import *

class getSound:
    def __init__(self, url):
        vargs = {'folders': False, 'group': False, 'track': '', 'num_tracks': 9223372036854775807, 'bandcamp': False,
                 'downloadable': False, 'likes': False, 'open': False, 'artist_url': url, 'keep': True}
        filenames = get_soundcloud(vargs)
        print(filenames)

getSound("https://soundcloud.com/iamganz/tell-me-ganz-flip")