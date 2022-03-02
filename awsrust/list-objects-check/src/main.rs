use aws_sdk_s3::{Client, Error};
use aws_sdk_s3::operation::ListObjectsV2;
use aws_smithy_http::operation::Operation;
use futures::{stream, StreamExt};
use http::header::HeaderName;

#[tokio::main]
async fn main() -> Result<(), Error> {
    env_logger::init();
    let shared_config = aws_config::load_from_env().await;
    let client = Client::new(&shared_config);
    let bucket = "jamesls-test-sync";
    let conf = aws_sdk_s3::Config::new(&shared_config);
    //let resp = client.list_objects_v2().bucket(bucket).send().await?;
    let low_level_client = aws_smithy_client::Builder::dyn_https()
        .middleware(aws_sdk_s3::middleware::DefaultMiddleware::new())
        .build();


    let operation = ListObjectsV2::builder()
        .bucket(bucket)
        .build()
        .unwrap()
        .make_operation(&conf)
        .await
        .unwrap();

    let (mut req, parts) = operation.into_request_response();
    /*
    req.augment(|mut inner_req: http::Request<aws_smithy_http::body::SdkBody>, _conf| -> Result<http::Request<aws_smithy_http::body::SdkBody>, Error> {
        inner_req.headers_mut().append(
            HeaderName::from_static("x-amz-checksum-mode"),
            "ENABLED".parse().unwrap(),
        );
        Ok(inner_req)
    });
     */
    req.http_mut().headers_mut().append(
        HeaderName::from_static("x-amz-checksum-mode"),
        "ENABLED".parse().unwrap(),
    );
    let reqclone = req.try_clone().unwrap();
    let newop = Operation::new(reqclone, parts.response_handler);

    let llresponse = low_level_client.call(newop)
        .await
        .expect("Should succeed");
    for obj in llresponse.contents().unwrap_or_default() {
        println!("{}", obj.key().unwrap_or_default());
    }

    /*
    let allreqs = stream::iter(resp.contents().unwrap_or_default()).map(
        |obj| {
            let client = &client;
            async move {
                let resp = client.head_object()
                    .bucket(bucket)
                    .key(obj.key().unwrap_or_default())
                    .send().await.unwrap();
                resp.e_tag.unwrap_or_default()
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
