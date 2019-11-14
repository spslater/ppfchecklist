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
py ppfchecklist.py WORKDIR [LOGFILE] [STDOUT]
```
`LOGFILE` defaults to `output.log` in `WORKDIR`.
The third argument must be `stdout` to also print to stdout and the logfile. Can't print to stdout and no logfile.

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

### '/<thing>': things
Only displays items for specific list named `thing`

## Editing
### Position
Can edit the position in the list.

## Contributing
Help is greatly appreciated. First check if there are any issues open that relate to what you want
to help with. Also feel free to make a pull request with changes / fixes you make.

## License
[MIT License](https://opensource.org/licenses/MIT)
