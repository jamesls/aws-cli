These examples show queries using the sample IMDB dataset.

The ``search`` subcommand requires the ``--endpoint-url`` argument.  You can
find the endpoint url for the search service using the ``aws cloudsearch
describe-domains`` command::

    $ aws cloudsearch describe-domains --domain-names testsearch --query DomainStatusList[].SearchService.Endpoint --output text
    search-testsearch-example.us-west-2.cloudsearch.amazonaws.com

To search for "katniss" and return just the titles you can run::

    $ aws cloudsearchdomain search --endpoint-url https://search-testsearch-example.us-west-2.cloudsearch.amazonaws.com --search-query katniss --return title

By default, the response is returned in JSON::

    {
        "status": {
            "rid": "y8/example=",
            "time-ms": 1
        },
        "hits": {
            "found": 4,
            "start": 0,
            "hit": [
                {
                    "fields": {
                        "title": "The Hunger Games: Mockingjay - Part 1"
                    },
                    "id": "tt1951265"
                },
                {
                    "fields": {
                        "title": "The Hunger Games: Catching Fire"
                    },
                    "id": "tt1951264"
                },
                {
                    "fields": {
                        "title": "The Hunger Games: Mockingjay - Part 2"
                    },
                    "id": "tt1951266"
                },
                {
                    "fields": {
                        "title": "The Hunger Games"
                    },
                    "id": "tt1392170"
                }
            ]
        }
    }

You can also specify which fields you want to search by specifying the
``--query-options`` argument.  For example, this query constrains the search
to the ``title`` and ``plot`` fields and boosts the importance of matches
in the ``title`` over matches in the ``plot`` field::


    $ aws cloudsearchdomain search --endpoint-url https://search-testsearch-example.us-west-2.cloudsearch.amazonaws.com --search-query katniss --return title --query-options '{"fields":["title^5","plot"]}'

The following example matches all movies in the sample data set that contain
*star* in the title, and either Harrison Ford or William Shatner appear in the
*actors* field, but Zachary Quinto does not.  It also uses the global
``--query`` argument to format the data to display just the titles, one
per line::

    $ aws cloudsearchdomain search --endpoint-url https://search-testsearch-example.us-west-2.cloudsearch.amazonaws.com --search-query "(and title:'star' (or actors:'Harrison Ford' actors:'William Shatner')(not actors:'Zachary Quinto'))" --query-parser structured --return title --query hits.hit[].[fields.title] --output text
    Star Wars
    Star Trek: The Wrath of Khan
    Star Trek: The Motion Picture
    Star Trek: Generations
    Star Wars: Episode VII
    Star Trek VI: The Undiscovered Country
    Star Trek IV: The Voyage Home
    Star Trek III: The Search for Spock
    Star Trek V: The Final Frontier
    Star Wars: Episode V - The Empire Strikes Back
