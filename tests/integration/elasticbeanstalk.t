  $ export AWS_DEFAULT_REGION=us-east-1
  $ aws elasticbeanstalk list-available-solution-stacks | jq '.SolutionStacks[]' | grep 32 | grep Python
  "32bit Amazon Linux running Python"
