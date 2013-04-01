  $ export AWS_DEFAULT_REGION=us-east-1
  $ aws directconnect describe-offerings | jq .offerings[0].location
  "CSOW"
