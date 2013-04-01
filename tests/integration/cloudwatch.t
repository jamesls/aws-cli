  $ export AWS_DEFAULT_REGION=us-east-1
  $ aws cloudwatch list-metrics | jq '.[].MetricName | select(. == "ProvisionedReadCapacityUnits")'
  "ProvisionedReadCapacityUnits"
  "ProvisionedReadCapacityUnits"
  "ProvisionedReadCapacityUnits"
  "ProvisionedReadCapacityUnits"
  "ProvisionedReadCapacityUnits"
  "ProvisionedReadCapacityUnits"
  "ProvisionedReadCapacityUnits"
  "ProvisionedReadCapacityUnits"
  "ProvisionedReadCapacityUnits"
  "ProvisionedReadCapacityUnits"
