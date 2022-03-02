#!/usr/bin/env python3
"""Experiments in improving listobjects performance."""
import time
import botocore.session


BUCKET = 'jamesls-jmes-sync'


def measure(func):
    def _do_measure(*args, **kwargs):
        t = time.time()
        result = func(*args, **kwargs)
        total_time = time.time() - t
        print(f"{func.__name__}: {total_time:.4f}")
        return result
    return _do_measure


@measure
def standard_list_objects(s3):
    paginator = s3.get_paginator('list_objects')
    pages = paginator.paginate(Bucket=BUCKET)
    count = 0
    for page in pages:
        for key in page['Contents']:
            count =+ 1
    print("Total objects: %s" % count)


def main():
    session = botocore.session.get_session()
    s3 = session.create_client('s3')
    standard_list_objects(s3)


if __name__ == '__main__':
    main()
