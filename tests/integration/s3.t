  $ export AWS_DEFAULT_REGION=us-east-1
  $ aws s3 create-bucket --bucket awsclitest1 && echo
  ""

Give it time to propogate

  $ sleep 5

  $ aws s3 list-buckets | jq '.Buckets[].Name' | grep awsclitest1
  *awsclitest1* (glob)

  $ aws s3 delete-bucket --bucket awsclitest1 && echo
  ""
