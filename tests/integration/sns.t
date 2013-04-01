  $ export AWS_DEFAULT_REGION=us-east-1
  $ TOPIC_ARN=$(aws sns create-topic --name testcli | jq '.TopicArn' | tr -d '"')

  $ echo $?
  0

  $ echo $TOPIC_ARN
  *arn:* (glob)

Now verify we can list the topic

  $ aws sns list-topics | jq '.[].TopicArn' | grep testcli
  *testcli* (glob)


  $ aws sns list-subscriptions-by-topic --topic-arn $TOPIC_ARN
  []* (glob)

  $ aws sns delete-topic --topic-arn $TOPIC_ARN > /dev/null
  $ echo $?
  0

