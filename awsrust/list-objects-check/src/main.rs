use aws_sdk_s3::{Client, Error};
use futures::{stream, StreamExt};

#[tokio::main]
async fn main() -> Result<(), Error> {
    let shared_config = aws_config::load_from_env().await;
    let client = Client::new(&shared_config);
    let bucket = "jamesls-test-sync";
    let resp = client.list_objects_v2().bucket(bucket).send().await?;
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
