// low level code adopted from: https://aws.amazon.com/blogs/developer/generate-presigned-url-modular-aws-sdk-javascript/
//const AWS = require('aws-sdk');
//const getSignedUrl = new AWS.S3RequestPresigner;
//const S3Client = new AWS.S3Client();

// SC 2023-03-07 : finaly directory structure from local side to cloud:
//    local image:  C:/Users/songc/PycharmProjects/ecbot/resource/runlogs/date/b0m0/win_chrome_amz_home/browse_search_kw/images/scrnsongc_yahoo_1678175548.png"
//    local skill:  C:/Users/songc/PycharmProjects/ecbot/resource/skills/public/win_chrome_amz_walk/scripts/skillname.psk
//
//       S3 image:  winrpa: /user_id/date/b0_m0/ +  win_app_site_page/skill_nam/images/scrnsongc_yahoo_1678175548.png
//       S3 skill:  winrpa: /user_id/ or /public/+ win_app_site_page/skills/skill_nam/scripts/skill_name.csk
//                  winrpa: /user_id/ or /public/+ win_app_site_page/skills/skill_nam/images/anchors***.png


const { getSignedUrl } = require("@aws-sdk/s3-request-presigner");

const { S3Client, GetObjectCommand, PutObjectCommand, DeleteObjectCommand, ListBucketsCommand, ListObjectsV2Command, HeadObjectCommand } = require("@aws-sdk/client-s3");

const { LambdaClient, AddLayerVersionPermissionCommand, InvokeCommand, createClientForDefaultRegion, LogType } = require("@aws-sdk/client-lambda");


var client;
var command;
var url;


const BUCKET = "winrpa";
const REGION = "us-east-1";
const URL_EXPR_TIME = 300;              //give it 5 minutes for any upload or download action.


const invoke = async (funcName, payload) => {
    const client = new LambdaClient({ region: REGION});
    const invokeCommand = new InvokeCommand({
        FunctionName: funcName,
        Payload: JSON.stringify(payload),
        LogType: LogType.Tail,
    });
      
    console.log("About to invoke s3presign....");
    const { Payload, LogResult } = await client.send(invokeCommand);
    console.log("returned  s3presign....");
    const result = Buffer.from(Payload).toString();
    const logs = Buffer.from(LogResult, "base64").toString();
    return { logs, result };
};

// check whether a file exists in a S3 bucket
async function exists(s3, inbucket, inkey) {
    var kexist = true;
    var params = {
        Bucket: inbucket,
        Key: inkey
    };
    var head_command;
    var head_response;
    console.log("checking existence. file....", params.Key);
    head_command = new HeadObjectCommand(params);
    
    try {
        head_response = await s3.send(head_command);
        
    } catch (error) {
        // handle error
        console.log("Error", error);
        kexist = false;
        console.log("file NOT exists");
    };
    
    return kexist;

}

function convertEmail(email) {
    // Replace the "@" with "_"
    let convertedEmail = email.replace("@", "_");

    // Replace all "." after the "@"
    const atIndex = convertedEmail.indexOf("_");
    if (atIndex !== -1) {
        const beforeAt = convertedEmail.substring(0, atIndex);
        const afterAt = convertedEmail.substring(atIndex + 1).replace(/\./g, "_");
        convertedEmail = beforeAt + "_" + afterAt;
    }

    return convertedEmail;
}


async function opFiles(user, reqfops, callback, logFlag) {
    var payload = { region : "us-east-1", requests : [] };
    var urls=[];
    var ls_command;
    var del_command;
    var ls_response;
    var del_response;
    var head_command;
    var head_response;
    var oe = true;
    var fdir;
    var fdirs;
    
    const user_parts = user.split("@");
    console.log("user:", user, " user_parts ", JSON.stringify(user_parts), user_parts[1], JSON.stringify(user_parts[1].split(".")));

    const user_domain = user_parts[1].split(".")[0];
    // const usr_name = user_parts[0].concat('_', user_domain);
    const usr_name = convertEmail(user)
    
    
    const s3config = {
        region: "us-east-1",
        credentials : {
            accessKeyId : process.env.StorageAWSKeyID,
            secretAccessKey : process.env.StorageAWSecret
        }
    };
    var s3client = new S3Client(s3config);
    var dir_resp = [];
    var start_idx;
    var os_app_site_page;
    var bxmx;
    var skill_name;
    var today = new Date();
    var today_words = today.toISOString().split('T')[0].split("-")
    var today_word = "D" + today_words[0] + today_words[1] + today_words[2]
    var local_user;
    var date_word;
    
    var prefix = "public/win/b0m0/chrome_amz_amazon_home/skills/browse_search_kw/images/";
    

    
    console.log("generating presigned URLs...", JSON.stringify(reqfops));
    

    var params = {
        FunctionName: 's3presign', // the lambda function we are going to invoke
        InvocationType: 'Event', // RequestResponse -  to get response from ChildLambda, Event - don't care the response (or error...)
        LogType: 'Tail',
        Payload: JSON.stringify(payload)
    };
  
    for (var fop of reqfops["fo"]) {
        console.log("working on file op......." + fop["op"]);
        
        if (fop["options"] != "") {
            prefix = fop["options"].split("|");
            if (prefix[0] == "screen") {
                fdirs = prefix[1].split("/")
                // look for runlogs, after it, will be botid, missionid, then os_app_site_page, then skill name, then images, then *.png
                // example resource/runlogs/date/b0m0/win_chrome_amz_home/browse_search_kw/images/scrnsongc_yahoo_1678175548.png"
                start_idx = fdirs.indexOf('runlogs');
                date_word = fdirs[start_idx + 2];
                bxmx = fdirs[start_idx + 3];
                os_app_site_page = fdirs[start_idx + 4];
                skill_name = fdirs[start_idx + 6];
                
                //now need to re-orgnized to the path on S3
                //S3 image:  winrpa: /user_id/date/b0_m0/ +  win_app_site_page/skill_nam/images/scrnsongc_yahoo_1678175548.png
                fdir = "runlogs/" + usr_name + "/" + date_word + "/" + bxmx + "/" + os_app_site_page + "/" + skill_name + "/images/";
            } else if (prefix[0] == "csk") {
                // look for skills, after it, will be user, then os_app_site_page, then scripts, then skillname.*sk
                fdirs = prefix[1].split(/[\/\\]/)
                if (fdirs.includes('public')) {
                    start_idx = fdirs.indexOf('skills');
                    local_user  = "public";
                } else {
                    start_idx = fdirs.indexOf('my_skills');
                    local_user  = usr_name;
                }
                
                os_app_site_page = fdirs[start_idx + 1];
                skill_name = fdirs[start_idx + 2];
                //now need to re-orgnized to the path on S3
                //  S3 skill:  winrpa: skills + /user_id/ or /public/+ win_app_site_page/skill_nam/scripts/skill_name.csk
                if (local_user == "public")  {
                    fdir = "skills/" + "public" + "/" + os_app_site_page + "/" + skill_name + "/scripts/";
                } else {
                    fdir = "skills/" + usr_name + "/" + os_app_site_page + "/" + skill_name + "/scripts/";
                }
    
            } else if (prefix[0] == "anchor") {
                // look for skills, after it, will be user, then os_app_site_page, then images, then skillname.*sk
                fdirs = prefix[1].split(/[\/\\]/)
                if (fdirs.includes('public')) {
                    start_idx = fdirs.indexOf('skills');
                    local_user  = "public";
                } else {
                    start_idx = fdirs.indexOf('my_skills');
                    local_user  = usr_name;
                }
                
                os_app_site_page = fdirs[start_idx + 1];
                skill_name = fdirs[start_idx + 2];
                //now need to re-orgnized to the path on S3
                //  S3 skill:  winrpa: skills + /user_id/ or /public/+ win_app_site_page/skill_nam/scripts/skill_name.csk
                if (local_user == "public")  {
                    fdir = "skills/" + "public" + "/" + os_app_site_page + "/" + skill_name + "/images/";
                } else {
                    fdir = "skills/" + usr_name + "/" + os_app_site_page + "/" + skill_name + "/images/";
                }       
            } else {
                // this is the general file exchange case, could be used for running external skill remotely.
                // so this requires input file name must starts with runlogs/...... and follow the standard
                // runlog path structure.
                const startIndex = prefix[1].indexOf("runlogs");

                if (startIndex !== -1) {
                    // Extract the substring starting from "runlogs"
                    let substring = prefix[1].substring(startIndex);
                    
                    // if (fop["op"] == "upload") {
                    //     // Replace "runlogs" with "runlogs/{user_name}"
                    //     // substring = substring.replace("runlogs", `runlogs/${usr_name}`);
                    // } else if (fop["op"] == "download") {
                    //     // Replace "runlogs" with "runlogs/{user_name}"
                    //     substring = prefix[1]
                    // }
                    fdir = substring + "/";
                } else {
                    fdir = prefix[1] + "/";
                }

                console.log("FDIR:"+fdir)
            }
        }
        
        switch (fop["op"]) {
          case "upload":
            console.log("working on upload processing");
            params = {
                Op : fop["op"],
                Bucket: BUCKET,
                Key: fdir+fop["names"],
                expire_in_s: URL_EXPR_TIME
            };
            payload.requests.push(params);
            break;
          case "download":
           params = {
               Op : fop["op"],
               Bucket: BUCKET,
               Key: fdir+fop["names"],
               expire_in_s: URL_EXPR_TIME
            };
            payload.requests.push(params);
            break;
          case "list":
            params = {
               Bucket: BUCKET,
               Prefix: fdir
            };
            console.log("list with prefix....", params.Prefix);
            ls_command = new ListObjectsV2Command(params);
            ls_response = await s3client.send(ls_command);
            dir_resp.push(ls_response);
            break;
          case "delete":
            params = {
               Bucket: BUCKET,
               Key: fdir+fop["names"]
            };
            console.log("deleting file....", params.Key);
            oe = await exists(s3client, params.Bucket, params.Key);
            del_command = new DeleteObjectCommand(params);
            del_response = await s3client.send(del_command);
            dir_resp.push(del_response);
            break;
          default:
        }
    }
    
    console.log("payload....", JSON.stringify(payload));

    
    if (payload.requests.length > 0) {
    
        try {
                console.log("Invoked Lambda...", JSON.stringify(payload));
                var urls = await invoke('s3presign', payload);
                console.log('Data: ', urls); // data maybe empty - {} when InvocationType is Event
                console.log("Lambda done");
      
                return {
                  "isBase64Encoded": false,
                  "statusCode": 202,
                  "headers": {},
                  "urls": urls
                };
            } catch (error) {
                // handle error
                console.log("Error", error);
                return {
                  "isBase64Encoded": false,
                  "statusCode": 500, // return error response
                  "headers": {},
                  "body": error.message
                };
            };
    } else {
        return {
          "isBase64Encoded": false,
          "statusCode": 202,
          "headers": {},
          "urls": dir_resp
        };
    }
    
    
}



// this function qualifies the API with the user account. Only qualified API is allowed to execute.
async function qualAPI(owner) {
  var payload = {   "region" : "us-east-1", 
                    "arguments": { "ops": [
                                            {
                                                "actid": "0",
                                                "op": "{\"action\":\"checkactive\"}",
                                                "options": "{\"email\":\""+owner+"\"}"
                                            }
                                        ]
                                },
                    "info": {
                        "fieldName": "reqAccountInfo",
                        "parentTypeName": "Query"
                    },
                    "identity": {"claims" : {"email": owner}}
      
                };

  
    try {
        console.log("Invoked Lambda...", JSON.stringify(payload));
        var result = await invoke('ecbAccountManager', payload);
        console.log('Data: ', result); // data maybe empty - {} when InvocationType is Event
        console.log("Call another lambda done");

        return {
          "isBase64Encoded": false,
          "statusCode": 200,
          "headers": {},
          "result": result
        };
    } catch (error) {
        // handle error
        console.log("Error", error);
        return {
          "isBase64Encoded": false,
          "statusCode": 500, // return error response
          "headers": {},
          "body": error.message
        };
    }
    
}


async function reportAccountSpending(owner, spending) {
  var payload = {   "region" : "us-east-1", 
                    "arguments": { "ops": [
                                            {
                                                "actid": "0",
                                                "op": "{\"spending\":"+spending.toString()+"}",
                                                "options": "{\"email\":\""+owner+"\"}"
                                            }
                                        ]
                                },
                    "info": {
                        "fieldName": "reportSpending",
                        "parentTypeName": "Query"
                    },
                    "identity": {"claims" : {"email": owner}}
      
                };

  
    try {
        console.log("Invoked Lambda...", JSON.stringify(payload));
        var result = await invoke('ecbAccountManager', payload);
        console.log('Data: ', result); // data maybe empty - {} when InvocationType is Event
        console.log("Call another lambda done");

        return {
          "isBase64Encoded": false,
          "statusCode": 200,
          "headers": {},
          "result": result
        };
    } catch (error) {
        // handle error
        console.log("Error", error);
        return {
          "isBase64Encoded": false,
          "statusCode": 500, // return error response
          "headers": {},
          "body": error.message
        };
    }
    
}

module.exports = { 
    opFiles,
    reportAccountSpending,
    qualAPI
};