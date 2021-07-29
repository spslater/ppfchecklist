# PPF Checklist
This flask app is a reading list to help keep track of comic books to read.

## Installation
```
pip install -r requirements.txt
```

### Why TinyDB?
[TinyDB's Documentation](https://tinydb.readthedocs.io/en/latest/intro.html#why-not-use-tinydb)
says not to use it for an HTTP server. Flask is an HTTP server, so why is it being used?

It boils down to this is not designed to be a scalable app used by a lot of people at once.
I prioritize the ability to easily read an modify the database by hand over the drawbacks.
The design of the database makes it easy to port to something like SQLite or MongoDB in the future
if I ever decide that the drawbacks start to outweigh using something like SQLite / MongoDB.
(I would probably lean towards SQLite becuase it's also a local database which I prefer.)

## Usage
```
usage: ppfchecklist.py [--help] [-e ENV]

optional arguments:
  --help             show this help message and exit
  -e ENV, --env ENV  File to load with environment settings (default: .env)
```

PPF Checklist loads it's settings from environment variables set. It defaults to looking for a
`.env` file but a specific file can be passed in with the `--env` flag. If that file can't be
found, the program will work with the values already set in the system environment.

See `.env.sample` for values that will be loaded from the environment and their defaults.

### list.db
TinyDB database where each entry has the comic `name`, `position`, and `date` completed in the `comics` table.
See `list.db.sample` for an example TinyDB database.

### tables.json
`tables.json` is a list of names for the different things you want to track.
See `tables.json.sample` for an example file.

## Endpoints
Done items are displayed below the list, with dates completed next to it.

### '/': index
Displays all lists on a single page

### '/\<thing>': things
Only displays items for specific list named `thing`

## Editing
### Position
Can edit the position in the list. A postition of `0` indicates the item is completed.
A position of `-1` indicates it's been dropped.

### Names
Can edit the title / name of an entry.

### Movement
Can move items between 2 different lists. Useful if a new sublist is created
like going from `tvshows` to `animated` and `live action`.

### Delete
Can delete items from a list if no longer being tracked.

## Single-Sign-On Authentication
SSO authentication can be enabled with the `-a` or `--authorize` flag.
It defaults to using a file named `client_secrets.json`.
When that is enabled, the `sso` json file with the client secretes must be preset.
See `client_secrets.json.sample` for an example file structure.

## Docker
`Dockerfile` to build the application and sample `docker-compose.yml.sample` are provided.
Build with `docker` and then you can run the docker-compose file from that.
The Docker image hasn't been uploaded publically yet.

## Contributing
Help is greatly appreciated. First check if there are any issues open that relate to what you want
to help with. Also feel free to make a pull request with changes / fixes you make.

## License
[MIT License](https://opensource.org/licenses/MIT)
