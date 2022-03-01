# Copyright 2014 Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"). You
# may not use this file except in compliance with the License. A copy of
# the License is located at
#
# http://aws.amazon.com/apache2.0/
#
# or in the "license" file accompanying this file. This file is
# distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF
# ANY KIND, either express or implied. See the License for the specific
# language governing permissions and limitations under the License.
import os
import time
import base64
import logging
import concurrent.futures

from awscli.botocore.httpchecksum import CrtCrc32cChecksum
from diskcache import Cache

from awscli.customizations.s3.syncstrategy.base import SizeAndLastModifiedSync


LOG = logging.getLogger(__name__)
CACHE_DIR = os.path.expanduser(
    os.path.join('~', '.aws', 'cli', 'cache', 's3')
)


JMES_SYNC_ARG = {
    'name': 'jmes-sync', 'action': 'store_true',
    'help_text': 'A fast, content-based syncing algorithm.'}


class HeadObjectLister:

    _CACHE_KEYS = {'ETag', 'Size', 'LastModified'}

    def __init__(self):
        # Key: (bucket, key) -> {'checksum': '<crc32c>'}
        #
        # If there's no checksum data available (wasn't stored with CRC32c)
        # then we set the checksum value to None to indicate that we've already
        # processed the key.
        # Key: (bucket, key) -> {'checksum': None}
        self._cache = {}
        self._client = None
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=30)
        self._stats = {'hits': 0, 'misses': 0}
        self._needs_primer_hack = True
        self._cache_per_bucket = {}

    def _get_cache(self, bucket):
        if bucket not in self._cache_per_bucket:
            path = os.path.join(CACHE_DIR, bucket)
            self._cache_per_bucket[bucket] = Cache(path)
        return self._cache_per_bucket[bucket]

    def set_client(self, client):
        self._client = client

    # Hook this method up to after-call.s3.ListObjects
    # so we can start queueing head object requests as soon
    # as we get a new set of objects.
    def on_list_objects_response(self, parsed, **kwargs):
        contents = parsed.get('Contents', [])
        bucket = parsed['Name']
        cache = self._get_cache(bucket)
        for content in contents:
            # We need to check if the cached content is up to date.  This is to
            # detect changes on the S3 side.
            cache_key = (bucket, content['Key'])
            if content['ChecksumAlgorithm'] != ['CRC32C']:
                cache[cache_key] = {'checksum': None}
                continue
            cached = cache.get(cache_key)
            if self._cache_outdated(cached, content):
                self._executor.submit(
                    self._get_remote_checksum, bucket=bucket, key=content['Key'])
            else:
                LOG.debug("Cache file is up to date, valid checksum.")
        if self._needs_primer_hack:
            # Give the HeadObject calls time to get going.  We could
            # replace this with just blocking on futures going forward.
            time.sleep(3)
            self._needs_primer_hack = False

    def _cache_outdated(self, cached, service_response):
        if cached is None:
            # No cache value, we need to do the HeadObject.
            return True
        actual = {k: service_response[k] for k in self._CACHE_KEYS}
        expected = {k: cached[k] for k in self._CACHE_KEYS}
        return cached == expected

    def _get_remote_checksum(self, bucket, key):
        cache = self._get_cache(bucket)
        head_object_params = {
            'Bucket': bucket,
            'Key': key,
            'ChecksumMode': 'ENABLED',
        }
        response = self._client.head_object(**head_object_params)
        checksum = base64.b64decode(response['ChecksumCRC32C'])
        cache[(bucket, key)] = {
            'checksum': checksum,
            # The names between ListObjects / HeadObject don't line up
            # exactly so we have to manually map these.
            'ETag': response['ETag'],
            'LastModified': response['LastModified'],
            'Size': response['ContentLength'],
        }

    def lookup_checksum(self, bucket, key):
        result = self._cache.get((bucket, key))
        if result is not None:
            LOG.debug("Checksum cache HIT for %s/%s", bucket, key)
            self._stats['hits'] += 1
        else:
            LOG.debug("Checksum cache MISS for %s/%s", bucket, key)
            self._stats['misses'] += 1
        LOG.debug(
            "Cache hit ratio: %.2f\n",
            self._stats['hits'] / float(sum(self._stats.values()))
        )
        return result


class JMESSync(SizeAndLastModifiedSync):

    ARGUMENT = JMES_SYNC_ARG

    def __init__(self, sync_type, head_object_lister=None):
        super(JMESSync, self).__init__(sync_type)
        if head_object_lister is None:
            head_object_lister = HeadObjectLister()
        self._client = None
        self._head_object_lister = head_object_lister

    def register_strategy(self, session):
        self._client = session.create_client('s3')
        self._head_object_lister.set_client(self._client)
        session.register(
            'after-call.s3.ListObjectsV2',
            self._head_object_lister.on_list_objects_response
        )
        session.set_stream_logger(
            'awscli.customizations.s3', log_level=logging.DEBUG)
        super(JMESSync, self).register_strategy(session)

    def determine_should_sync(self, src_file, dest_file):
        """Subclasses should implement this method.

        This function takes two ``FileStat`` objects (one from the source and
        one from the destination).  Then makes a decision on whether a given
        operation (e.g. a upload, copy, download) should be allowed
        to take place.

        The function currently raises a ``NotImplementedError``.  So this
        method must be overwritten when this class is subclassed.  Note
        that this method must return a Boolean as documented below.

        :type src_file: ``FileStat`` object
        :param src_file: A representation of the operation that is to be
            performed on a specific file existing in the source.  Note if
            the file does not exist at the source, ``src_file`` is None.

        :type dest_file: ``FileStat`` object
        :param dest_file: A representation of the operation that is to be
            performed on a specific file existing in the destination. Note if
            the file does not exist at the destination, ``dest_file`` is None.

        :rtype: Boolean
        :return: True if an operation based on the ``FileStat`` should be
            allowed to occur.
            False if if an operation based on the ``FileStat`` should not be
            allowed to occur. Note the operation being referred to depends on
            the ``sync_type`` of the sync strategy:

            'file_at_src_and_dest': refers to ``src_file``

            'file_not_at_dest': refers to ``src_file``

            'file_not_at_src': refers to ``dest_file``
        """
        # The file type we get has this info:
        #
        # {'compare_key': '.jmessync.py.swp',
        #  'dest': 'jamesls-test-sync/foo/jmessync.py',
        #  'dest_type': 's3',
        #  'last_update': datetime.datetime(2022, 2, 28, 14, 8, 42, 821268, tzinfo=tzlocal()),
        #  'operation_name': 'upload',
        #  'response_data': None,
        #  'size': 12288,
        #  'src': '/path/to/file/jmessync.py',
        #  'src_type': 'local'}

        # The dest_file for an upload has response data:
        #{'compare_key': '.jmessync.py.swp',
        # 'dest': '/Users/jamessar/Source/aws-cli/awscli/customizations/s3/syncstrategy/.jmessync.py.swp',
        # 'dest_type': 'local',
        # 'last_update': datetime.datetime(2022, 2, 28, 14, 8, 32, tzinfo=tzlocal()),
        # 'operation_name': '',
        # 'response_data': {'ChecksumAlgorithm': ['CRC32C'],
        #                   'ETag': '"dbfe767abb9e224fead3ac420cdcaff0"',
        #                   'Key': 'foo/.jmessync.py.swp',
        #                   'LastModified': datetime.datetime(2022, 2, 28, 14, 8, 32, tzinfo=tzlocal()),
        #                   'Size': 12288,
        #                   'StorageClass': 'STANDARD'},
        # 'size': 12288,
        # 'src': 'jamesls-test-sync/foo/.jmessync.py.swp',
        # 'src_type': 's3'}
        result = None
        operation = src_file.operation_name
        if operation == 'upload':
            result = self._handle_upload_check(src_file, dest_file)
        elif operation == 'download':
            result = self._handle_download_check(src_file, dest_file)
        if result is None:
            LOG.debug(
                "Missing checksum data, falling back to default "
                "sync strategy.")
            return super(JMESSync, self).determine_should_sync(
                src_file, dest_file)
        else:
            LOG.debug("Checksum comparison: %s", result)
        return result

    def _handle_upload_check(self, src_file, dest_file):
        if dest_file.response_data.get('ChecksumAlgorithm', '') != ['CRC32C']:
            return None
        bucket, key = src_file.dest.split('/', 1)
        actual_checksum = self._get_remote_checksum(bucket, key)
        local_checksum = self._compute_local_checksum(src_file.src)
        return not actual_checksum == local_checksum

    def _get_remote_checksum(self, bucket, key):
        checksum = self._head_object_lister.lookup_checksum(
            bucket=bucket, key=key)
        if checksum is None:
            # If we don't have the checksum, we return an empty string, which
            # will fail the equality check and force a download.  We could
            # alternatively just block until we get the HeadObject result if we
            # wanted.
            return ''
        return checksum['checksum']

    def _handle_download_check(self, src_file, dest_file):
        if src_file.response_data.get('ChecksumAlgorithm', '') != ['CRC32C']:
            return None
        bucket, key = src_file.src.split('/', 1)
        actual_checksum = self._get_remote_checksum(bucket, key)
        local_checksum = self._compute_local_checksum(src_file.dest)
        return not actual_checksum == local_checksum

    def _compute_local_checksum(self, filename):
        with open(filename, 'rb') as f:
            c = CrtCrc32cChecksum()
            c.update(f.read())
            return c.digest()



class MerkleTree:
    def __init__(self, checksum_cls):
        self._checksum_cls = checksum_cls

    def calculate_tree_hash(self, dirname):
        hashes = []
        contents = os.listdir(dirname)
        for obj in contents:
            full_path = os.path.join(dirname, obj)
            if os.path.isfile(full_path):
                hashes.append(
                    {'path': full_path,
                     'checksum': self._compute_local_checksum(full_path)}
                )
            elif os.path.isdir(full_path):
                checksum = self.calculate_tree_hash(full_path)
                hashes.append(checksum)
        final = self._checksum_cls()
        for chunk in hashes:
            final.update(chunk['checksum'])
        return {'path': dirname, 'checksum': final.digest()}

    def _compute_local_checksum(self, filename):
        with open(filename, 'rb') as f:
            c = self._checksum_cls()
            c.update(f.read())
            return c.digest()



#t = MerkleTree(CrtCrc32cChecksum)
#print(t.calculate_tree_hash('.'))
