# PPF Checklist
This flask app is a reading list to help keep track of comic books to read.

## Installation
```
pip install -r requirements.txt
```

## Upgrade
Upgrading from the previous TinyDB version of PPF Checklist just requires going to the `/upload` endpoint and selecting the old database. The tables will be in alphabetical order instead of the order assigned previously.

## Usage
```py -m flask run``

PPF Checklist loads it's settings from environment variables set. It defaults to using for a
`.flaskenv` and `.env` file

See `.flaskenv` for values that will be loaded from the environment and their defaults.

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
