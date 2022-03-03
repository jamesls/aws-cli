//use aws_config::Config;
use http::HeaderValue;
use aws_sdk_s3::{Client, Error};
use aws_sdk_s3::middleware::DefaultMiddleware;
use aws_sdk_s3::operation::HeadObject;
use aws_smithy_client::erase::DynConnector;
use aws_smithy_http::operation::Operation;
use futures::{stream, StreamExt};
use http::header::HeaderName;
use std::fs::File;
use std::io::Read;
use serde::{Deserialize, Serialize};


#[derive(Serialize, Deserialize, Debug)]
struct ObjKeys {
    keys: Vec<String>,
}

async fn batch_head_objects(low_level_client: aws_smithy_client::Client<DynConnector, DefaultMiddleware>,
                            conf: aws_sdk_s3::Config,
                            bucket: &str, keys: Vec<String>) -> () {
    // Figure out how to get _result working.
    let mut _result: Vec<String> = vec! [];
    let allreqs = stream::iter(keys).map(
        |obj| {
            let llclient = &low_level_client;
            let newconf = &conf;
            async move {
                let headobj_op = HeadObject::builder()
                    .bucket(bucket)
                    .key(obj)
                    .build()
                    .unwrap()
                    .make_operation(newconf)
                    .await
                    .unwrap();

                let (mut req, parts) = headobj_op.into_request_response();
                req.http_mut().headers_mut().append(
                    HeaderName::from_static("x-amz-checksum-mode"),
                    "ENABLED".parse().unwrap(),
                );
                let reqclone = req.try_clone().unwrap();
                let newop = Operation::new(reqclone, parts.response_handler);

                let llresponse = llclient.call_raw(newop)
                    .await
                    .expect("Should not fail");
                let defaultvalue = HeaderValue::from_static("");
                let value = llresponse.raw
                    .http()
                    .headers()
                    .get("x-amz-checksum-crc32c").unwrap_or(&defaultvalue);
                let actual = value.to_str();
                let unwrapped = actual.unwrap();
                String::from(unwrapped)
            }
        }
    ).buffer_unordered(30);
    allreqs.for_each(|headobj_resp|
        async move {
          println!("{}", headobj_resp)
    }).await;
}

#[tokio::main]
async fn main() -> Result<(), Error> {
    env_logger::init();

    let bucket = std::env::args().nth(1).expect("no bucket given");
    let filename = std::env::args().nth(2).expect("no filename given");
    let mut file = File::open(filename).unwrap();
    let mut data = String::new();
    file.read_to_string(&mut data).unwrap();
    let objkeys: ObjKeys = serde_json::from_str(&data).unwrap();


    let shared_config = aws_config::load_from_env().await;
    let _client = Client::new(&shared_config);
    let conf = aws_sdk_s3::Config::new(&shared_config);
    //let resp = client.list_objects_v2().bucket(bucket).send().await?;
    let low_level_client = aws_smithy_client::Builder::dyn_https()
        .middleware(aws_sdk_s3::middleware::DefaultMiddleware::new())
        .build();
    batch_head_objects(
        low_level_client, conf, &bucket, objkeys.keys).await;
    //println!("{:?}", response);




    /*
    let operation = ListObjectsV2::builder()
        .bucket(bucket)
        .build()
        .unwrap()
        .make_operation(&conf)
        .await
        .unwrap();

    let (mut req, parts) = operation.into_request_response();
    req.http_mut().headers_mut().append(
        HeaderName::from_static("x-amz-checksum-mode"),
        "ENABLED".parse().unwrap(),
    );
    let reqclone = req.try_clone().unwrap();
    let newop = Operation::new(reqclone, parts.response_handler);

    let llresponse = low_level_client.call(newop)
        .await
        .expect("Should succeed");
    let allreqs = stream::iter(llresponse.contents().unwrap_or_default()).map(
        |obj| {
            let llclient = &low_level_client;
            let newconf = &conf;
            async move {
               let headobj_op = HeadObject::builder()
                   .bucket(bucket)
                   .key(obj.key().unwrap_or_default())
                   .build()
                   .unwrap()
                   .make_operation(newconf)
                   .await
                   .unwrap();

                let (mut req, parts) = headobj_op.into_request_response();
                req.http_mut().headers_mut().append(
                    HeaderName::from_static("x-amz-checksum-mode"),
                    "ENABLED".parse().unwrap(),
                );
                let reqclone = req.try_clone().unwrap();
                let newop = Operation::new(reqclone, parts.response_handler);

                let llresponse = llclient.call_raw(newop)
                    .await
                    .expect("Should not fail");
                let defaultvalue = HeaderValue::from_static("");
                let value = llresponse.raw
                    .http()
                    .headers()
                    .get("x-amz-checksum-crc32c").unwrap_or(&defaultvalue);
                let actual = value.to_str();
                let unwrapped = actual.unwrap();
                String::from(unwrapped)
            }
        }
    ).buffer_unordered(30);
    allreqs.for_each(|headobj_resp| async move {
        println!("{}", headobj_resp);
    }).await;
     */



    /* This is unbounded and you'll get errors about too many open files.
    let allreqs = future::join_all(
        resp.contents().unwrap_or_default().into_iter().map(|obj| {
            let client = &client;
            async move {
                let resp = client.head_object()
                    .bucket(bucket).key(obj.key().unwrap_or_default())
                    .send().await.unwrap();
                resp.e_tag.unwrap_or_default()
            }
    }))
    .await;
    for etag in allreqs {
        println!("{}", etag);
    }
    */

    /* This is a version that worked.
    for obj in resp.contents().unwrap_or_default() {
        let key = obj.key().unwrap_or_default();
        let headobj_req = client.head_object().bucket(bucket).key(key);
        let headobj_resp = headobj_req.send().await?;
        println!("{}", headobj_resp.e_tag().unwrap_or_default());
    }
     */

    Ok(())
}
