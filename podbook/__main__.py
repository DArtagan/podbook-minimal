#!/usr/bin/env python3

import collections
import datetime
import functools
import glob
import mutagen.easyid3
import os
import re
import uuid
import sys

import feedgen.feed
import flask
import yaml


DEBUG_MODE = os.environ.get('DEBUG', False)

UUID_NAMESPACE = uuid.UUID(os.environ.get('UUID_NAMESPACE', uuid.uuid4()))

AUTH_USERNAME = os.environ.get('AUTH_USERNAME', False)
AUTH_PASSWORD = os.environ.get('AUTH_PASSWORD', False)
REQUIRE_AUTH = AUTH_USERNAME and AUTH_PASSWORD

FORMATS = ['mp3', 'm4b']

if DEBUG_MODE: print('*** RUNNING IN DEBUG MODE ***')
if not REQUIRE_AUTH: print('*** RUNNING WITHOUT AUTHENTICATION ***')

app = flask.Flask(__name__)


def requires_auth(f):
    """If we set a username and password, require it for this request."""

    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if REQUIRE_AUTH:
            auth = flask.request.authorization
            if not auth or AUTH_USERNAME != auth.username or AUTH_PASSWORD != auth.password:
                return flask.Response('Must authenticate', 401, {'WWW-Authenticate': 'Basic realm="Login Required"'})

        return f(*args, **kwargs)
    return decorated


def list_books():
    """List all known books as (author, title) tuples."""

    for author in os.listdir('books'):
        author_path = os.path.join('books', author)
        if not os.path.isdir(author_path):
            continue

        for title in os.listdir(author_path):
            book_path = os.path.join(author_path, title)
            if not os.path.isdir(book_path):
                continue

            if not any(file.endswith(tuple(FORMATS)) for file in os.listdir(book_path)):
                continue

            yield(author, title)


def book_to_uuid(author, title):
    """Translate a book folder into a deterministic UUID."""

    return uuid.uuid5(UUID_NAMESPACE, author + title)


def uuid_to_book(id, cache = {}):
    """Translate a UUID from above back into a book folder."""

    if not isinstance(id, uuid.UUID):
        id = uuid.UUID(id)

    if not id in cache:
        cache.clear()
        for author, title in list_books():
            cache[book_to_uuid(author, title)] = (author, title)

    if not id in cache:
        raise Exception('{} does not match any known book'.format(id))

    return cache[id]


@app.route('/')
@requires_auth
def index():
    library = collections.defaultdict(list)
    for author, title in list_books():
        book = (title, book_to_uuid(author, title))
        library[author].append(book)
    return flask.render_template('index.html', library=library)


@app.route('/feed/<uuid>.xml')
def get_feed(uuid):
    author, title = uuid_to_book(uuid)

    fg = feedgen.feed.FeedGenerator()
    fg.load_extension('podcast')

    host_url = flask.request.scheme + '://' + flask.request.host
    feed_link = host_url + '/feed/{uuid}.xml'.format(uuid=uuid)

    fg.id = feed_link
    fg.title(title)
    fg.description('{title} by {author}'.format(title=title, author=author))
    fg.author(name=author)
    fg.link(href=feed_link, rel='alternate')

    images = [os.path.basename(i) for i in glob.glob(os.path.join('books', author, title, 'cover*'))]
    if images:
        url = host_url + '/media/{author}/{title}/{image}'.format(author=author, title=title, image=images[0])
        fg.image(url)
        fg.podcast.itunes_image(url)

    fg.podcast.itunes_category('Arts')

    def get_tracknumber_from_file(filepath):
        try:
            track = mutagen.easyid3.EasyID3(filepath)['tracknumber'][0]
            return int(re.match('\d+', track).group(0))
        except mutagen.MutagenError:
            return 0

    files = glob.glob(os.path.join('books', author, title, '*'))
    files = sorted(files, key=get_tracknumber_from_file)
    files = [os.path.basename(i) for i in files]
    initial_time = datetime.datetime.utcfromtimestamp(os.path.getmtime(os.path.join('books', author, title, files[0])))

    for index, file in enumerate(files):
        if not file.endswith(tuple(FORMATS)):
            continue

        feed_entry_link = host_url + '/media/{author}/{title}/{file}'.format(author=author, title=title, file=file)
        feed_entry_link = feed_entry_link.replace(' ', '%20')

        fe = fg.add_entry()

        try:
            track = mutagen.easyid3.EasyID3(filepath)
            name = ' '.join(track['title'])
        except:
            name = file.rsplit('.', 1)[0]

        fe.id(feed_entry_link)
        fe.title(name)
        fe.description('{title} by {author} - {chapter}'.format(
            title = title,
            author = author,
            chapter = name,
        ))
        fe.pubdate('{} +0000'.format(initial_time + datetime.timedelta(seconds=90 * index)))
        fe.enclosure(feed_entry_link, 0, 'audio/mpeg')

    return fg.rss_str(pretty=True)


if __name__ == '__main__':
    app.run(host = '0.0.0.0', debug=DEBUG_MODE)

