These just verify that we can run help on the various AWS services.
This ensures that all the data paths and everything are wired up correctly.

  $ aws ec2 help | head -n 1
  EC2(1)                              aws-cli                             EC2(1)

  $ aws help | head -n 1
  AWS(1)                              aws-cli                             AWS(1)

  $ aws s3 help | head -n 1
  S3(1)                               aws-cli                              S3(1)

  $ aws ec2 describe-instances help | head -n 1
  EC2-DESCRIBE-INSTANCES(1)           aws-cli          EC2-DESCRIBE-INSTANCES(1)
