  $ export AWS_DEFAULT_REGION=us-east-1
  $ aws cloudformation describe-stacks | jq .[0].StackId | grep arn
  *arn:* (glob)
