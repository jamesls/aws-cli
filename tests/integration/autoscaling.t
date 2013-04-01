  $ export AWS_DEFAULT_REGION=us-east-1
  $ aws autoscaling describe-adjustment-types | jq .AdjustmentTypes[0].AdjustmentType
  "ChangeInCapacity"
