// const AWS = require('aws-sdk');
//const AWSAS = require('aws-sdk/client-appsync');
//const AppSyncClient = new AWS.AppSync({ region: "us-east-1" });
//const AppSyncClient = require('aws-sdk/client-appsync');
// const AWS = require('/mnt/efs/access/layers/usefull0/node_modules/aws-sdk');
// import fetch from "node-fetch";
// import AWS from 'aws-sdk';
const path = require('path');
const fs = require('fs');
const { pipeline } = require("stream/promises");
const { getSignedUrl } = require("@aws-sdk/s3-request-presigner");
const crypto = require("crypto");

// Test module is optional - only used in test mode
let ut = { testcases: [] };
try {
  ut = require("./test");
} catch (e) {
  // test.js not included in production deployment
}
const cfiles = require("./cfiles");
const util = require("./botutil");
const agentService = require("./services/agentService");
const taskService = require("./services/taskService");
const skillService = require("./services/skillService");
const skillAssetService = require("./services/skillAssetService");
const skillEditorService = require("./services/skillEditorService");
const toolService = require("./services/toolService");
const knowledgeService = require("./services/knowledgeService");
const vehicleService = require("./services/vehicleService");
const orgService = require("./services/orgService");
const avatarService = require("./services/avatarService");
const promptService = require("./services/promptService");
const settingsService = require("./services/settingsService");

// const axios = require('axios');

//const nodemailer = require('nodemailer');
const lzstring = require("./lzstring");

//const RDS = new AWS.RDSDataService();
//var SES = new AWS.SES({ region: "us-east-1" });

// const { RDS, AddRoleToDBClusterCommand } = require("@aws-sdk/client-rds");
const { SESClient, SendRawEmailCommand } = require("@aws-sdk/client-ses");
const { util_utf8_node } = require("@aws-sdk/util-utf8-node");
const { DynamoDBClient, GetItemCommand } = require("@aws-sdk/client-dynamodb");
const dynClient = new DynamoDBClient({ region: "us-east-1" });
const { SQSClient, SendMessageCommand, ReceiveMessageCommand, DeleteMessageCommand, GetQueueAttributesCommand } = require('@aws-sdk/client-sqs');
const { S3Client, GetObjectCommand, PutObjectCommand, HeadObjectCommand, ListObjectsV2Command, CopyObjectCommand } = require("@aws-sdk/client-s3");

// Initialize the SQS client
const sqsClient = new SQSClient({ region: 'us-east-1' }); // Set your AWS region


const s3 = new S3Client({ region: 'us-east-1' });

const { RDSDataClient, ExecuteStatementCommand  } = require("@aws-sdk/client-rds-data");

const RDS = new RDSDataClient({ region: "us-east-1" });
const rdsClient = RDS;


const BUCKET_NAME = "winrpa";
const IAM_USER_KEY = "YOUR_IAM_USER_KEY";
const IAM_USER_SECRET = "YOUR_IAM_USER_SECRET";
//const S3 = new AWS.S3();
const LOG_ROOT = process.env.LOG_ROOT;

const UNKNOWN_DEVICE = Error("Unknown device");
const ALLOWED_ORIGIN = "https://www.iotton.com";

const SUPER_USERS = new Set([
  "songc@yahoo.com",
  "songc_yahoo_com",
  "dbcabea3-1fcb-461b-abe9-df54723db582",
  "dbcabea3_1fcb_461b_abe9_df54723db582",
  "google_105649646860146222891",
  "249511118@qq.com"
]);

const EXEMPT_USERS = new Set([
  "songc_yahoo_com",
  "songc@yahoo.com",
  "dbcabea3-1fcb-461b-abe9-df54723db582",
  "dbcabea3_1fcb_461b_abe9_df54723db582"
]);

const SUBSCRIPTION_REQUIRED_FIELDS = new Set([
  "addAgentTasks",
  "removeAgentTasks",
  "updateAgentTasks",
  "addAgentSkills",
  "removeAgentSkills",
  "updateAgentSkills",
  "addAgentTools",
  "removeAgentTools",
  "updateAgentTools",
  "addAgentKnowledges",
  "removeAgentKnowledges",
  "updateAgentKnowledges",
  "updateAgentTasksExStatus",
  "addVehicles",
  "updateVehicles",
  "removeVehicles",
  "addOrgs",
  "updateOrgs",
  "removeOrgs",
  "addAvatars",
  "updateAvatars",
  "removeAvatars",
  "addAvatarResources",
  "updateAvatarResources",
  "removeAvatarResources",
  "addPrompts",
  "updatePrompts",
  "removePrompts",
  "addAgentTools",
  "removeAgentTools",
  "updateAgentTools",
  "addKnowledges",
  "removeKnowledges",
  "updateKnowledges",
  "addAgents",
  "removeAgents",
  "updateAgents",
  "getAgents",
  "getAgentSkills",
  "getAgentTasks",
  "getAgentTools",
  "getKnowledges",
  "queryAgents",
  "queryAgentSkills",
  "queryAgentTasks",
  "queryAgentTools",
  "queryKnowledges",
  "getVehicles",
  "queryVehicles",
  "getPrompts",
  "queryPrompts",
  "getOrgs",
  "queryOrgs",
  "getOrgTree",
  "getOrgAgentTree",
  "getAvatars",
  "queryAvatars",
  "getAvatarResources",
  "queryAvatarResources",
  "getAllMine"
]);

const Cluster = process.env.DBAuroraClusterArn;
const DB = process.env.DatabaseName;
const Secrets = process.env.DBSecretsStoreArn;
const queueUrl = process.env.LabelQueueArn;


const APPSYNC_URL = 'https://3oqwpjy5jzal7ezkxrxxmnt6tq.appsync-api.us-east-1.amazonaws.com/graphql';
// const APPSYNC_API_KEY = process.env.GQL_API_KEY;
const APPSYNC_API_KEY = "da2-hwmqigvtbfai7pbl7zfah76fly";
const AVATAR_BUCKET = process.env.AVATAR_BUCKET || "ecan-avatars";
const AVATAR_ROOT_PREFIX = process.env.AVATAR_ROOT_PREFIX || "avatars";
const SKILL_BUCKET = process.env.SKILL_BUCKET || "ecan-skills";


const MAXBOTINTS = 5;

var owner;
var statCode = 200;
var errMsg = "None";

var startStep = 0;
                        
// 2025-06-23 SC - Going fully agentic, adopt code from botScheduler.js
//
var logFlag = { "anyfunc":false, 
                "err": true,
                "createNewAgentsStatement": true,
                "addAgents": true,
                "createRemoveAgentsStatement": true,
                "removeAgents": true,
                "createUpdateAgentsStatement": true,
                "updateAgents": true,
                "createQueryAgentsStatement": true,
                "queryAgents": true,
                "getAgents": true,
                "getAgentsByIds": true,
                "createQueryAfterAddAgentsStatement": true,
                "queryAgentsAfterAdd": true,

                "createNewAgentSkillsStatement": true,
                "addAgentSkills": true,
                "createRemoveAgentSkillsStatement": true,
                "removeAgentSkills": true,
                "createUpdateAgentSkillsStatement": true,
                "updateAgentSkills": true,
                "createQueryAgentSkillsStatement": true,
                "queryAgentSkills": true,
                "getAgentSkillsByIds": true,
                "getAgentSkills": true,

                "createNewAgentTasksStatement": true,
                "addAgentTasks": true,
                "createRemoveAgentTasksStatement": true,
                "removeAgentTasks": true,
                "createUpdateAgentTasksStatement": true,
                "updateAgentTasks": true,
                "createQueryAgentTasksStatement": true,
                "queryAgentTasks": true,
                "getAgentTasks": true,
                "getAgentTasksByIds": true,

                "createNewAgentToolsStatement": true,
                "addAgentTools": true,
                "createRemoveAgentToolsStatement": true,
                "removeAgentTools": true,
                "createUpdateAgentToolsStatement": true,
                "updateAgentTools": true,
                "createQueryAgentToolsStatement": true,
                "queryAgentTools": true,
                "getAgentTools": true,
                "getAgentToolsByIds": true,
                
                "createNewKnowledgesStatement": true,
                "addKnowledges": true,
                "createRemoveKnowledgesStatement": true,
                "removeKnowledges": true,
                "createUpdateKnowledgesStatement": true,
                "updateKnowledges": true,
                "createQueryKnowledgesStatement": true,
                "queryKnowledges": true,
                "getKnowledges": true,
                "getKnowledgesByIds": true,
                
                "rdsExecute": true,
                "rdsBatchExecute": true,
                
                "loggers":["anyone"]
              };

function normalizePathSegment(seg) {
  if (!seg) return "";
  return seg.replace(/^\/+|\/+$/g, "");
}

function pickFileName(preferredPath, fallbackBase) {
  if (preferredPath) {
    const base = path.basename(preferredPath);
    if (base) return base;
  }
  return fallbackBase;
}

async function ensurePrefixExists(bucket, prefix) {
  const key = prefix.endsWith("/") ? prefix : `${prefix}/`;
  await s3.send(new PutObjectCommand({ Bucket: bucket, Key: key, Body: "" }));
}

async function objectExists(bucket, key) {
  try {
    await s3.send(new HeadObjectCommand({ Bucket: bucket, Key: key }));
    return true;
  } catch (err) {
    if (err.$metadata?.httpStatusCode === 404 || err.name === "NotFound" || err.Code === "NotFound") {
      return false;
    }
    throw err;
  }
}

async function prepareAvatarUploadTargets({ avatar, ownerEmail, ownerSub, generatedId, skipExistCheck = false }) {
  const ownerFolder = ownerSub || normalizePathSegment(ownerEmail) || "unknown";
  const basePrefix = `${AVATAR_ROOT_PREFIX}/${ownerFolder}`;

  const imagePrefixRoot = normalizePathSegment(avatar.cloud_image_key) || "";
  const videoPrefixRoot = normalizePathSegment(avatar.cloud_video_key) || "";

  const imagePrefix = imagePrefixRoot ? `${basePrefix}/${imagePrefixRoot}` : basePrefix;
  const videoPrefix = videoPrefixRoot ? `${basePrefix}/${videoPrefixRoot}` : basePrefix;

  const imageFileName = pickFileName(avatar.image_path, `${generatedId}-image`);
  const videoFileName = pickFileName(avatar.video_path, `${generatedId}-video`);

  const imageKey = `${imagePrefix}/images/${imageFileName}`;
  const videoKey = `${videoPrefix}/videos/${videoFileName}`;

  await ensurePrefixExists(AVATAR_BUCKET, `${imagePrefix}/images`);
  await ensurePrefixExists(AVATAR_BUCKET, `${videoPrefix}/videos`);

  if (!skipExistCheck) {
    if (await objectExists(AVATAR_BUCKET, imageKey)) {
      return { error: `FILE_EXISTS: ${imageKey}` };
    }
    if (await objectExists(AVATAR_BUCKET, videoKey)) {
      return { error: `FILE_EXISTS: ${videoKey}` };
    }
  }

  const image_upload_url = await getSignedUrl(
    s3,
    new PutObjectCommand({ Bucket: AVATAR_BUCKET, Key: imageKey }),
    { expiresIn: 900 }
  );
  const video_upload_url = await getSignedUrl(
    s3,
    new PutObjectCommand({ Bucket: AVATAR_BUCKET, Key: videoKey }),
    { expiresIn: 900 }
  );

  return {
    imageKey,
    videoKey,
    image_upload_url,
    video_upload_url
  };
}

/**
 * Add presigned GET URLs for avatar S3 objects.
 * Attaches presigned_image_url and presigned_video_url to each record.
 * URLs expire in 1 hour (3600s).
 */
async function presignAvatarRecords(records, expiresIn = 3600) {
  if (!Array.isArray(records) || records.length === 0) return records;
  return Promise.all(records.map(async (r) => {
    const out = { ...r };
    try {
      if (r.cloud_image_key) {
        out.presigned_image_url = await getSignedUrl(
          s3,
          new GetObjectCommand({ Bucket: AVATAR_BUCKET, Key: r.cloud_image_key }),
          { expiresIn }
        );
      }
      if (r.cloud_video_key) {
        out.presigned_video_url = await getSignedUrl(
          s3,
          new GetObjectCommand({ Bucket: AVATAR_BUCKET, Key: r.cloud_video_key }),
          { expiresIn }
        );
      }
    } catch (err) {
      console.warn(`[agentScheduler] presignAvatarRecords: failed for id=${r.id}:`, err.message);
    }
    return out;
  }));
}

function normalizeEmailForPath(email) {
  if (!email) return "unknown";
  return email.replace(/[@.]/g, "_");
}

async function streamToString(stream) {
  if (!stream) return "";
  const chunks = [];
  for await (const chunk of stream) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  return Buffer.concat(chunks).toString("utf-8");
}

async function listAllObjects(bucket, prefix) {
  const keys = [];
  let continuationToken;
  do {
    const res = await s3.send(new ListObjectsV2Command({
      Bucket: bucket,
      Prefix: prefix,
      ContinuationToken: continuationToken
    }));
    const contents = res.Contents || [];
    for (const obj of contents) {
      if (obj?.Key) keys.push(obj.Key);
    }
    continuationToken = res.IsTruncated ? res.NextContinuationToken : undefined;
  } while (continuationToken);
  return keys;
}

async function ensureUserSkillFolders(bucket, userPrefix) {
  const prefixes = ["settings", "prompts", "skills", "contexts", "logs", "my_labels", "my_products", "my_warehouses"];
  await ensurePrefixExists(bucket, userPrefix);
  for (const dir of prefixes) {
    await ensurePrefixExists(bucket, `${userPrefix}${dir}`);
  }
}

/**
 * Read all *.json files from an S3 prefix and return parsed objects.
 * Each object gets _filepath and _filename injected.
 */
async function readJsonDir(bucket, prefix) {
  const keys = await listAllObjects(bucket, prefix);
  const jsonKeys = keys.filter(k => k.endsWith(".json") && !k.endsWith("/"));
  const results = [];
  for (const key of jsonKeys) {
    try {
      const res = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: key }));
      const raw = await streamToString(res.Body);
      const parsed = JSON.parse(raw);
      const obj = Array.isArray(parsed) ? parsed : [parsed];
      for (const item of obj) {
        if (item && typeof item === "object") {
          item._filepath = key;
          item._filename = key.split("/").pop();
          results.push(item);
        }
      }
    } catch (err) {
      console.warn(`[agentScheduler] readJsonDir: skip ${key}: ${err.message}`);
    }
  }
  return results;
}

/**
 * Write a JSON item to S3.  Key = prefix/id.json
 */
async function writeJsonItem(bucket, prefix, id, data) {
  const key = `${prefix}/${id}.json`;
  const clean = { ...data };
  delete clean._filepath;
  delete clean._filename;
  await s3.send(new PutObjectCommand({
    Bucket: bucket,
    Key: key,
    Body: JSON.stringify(clean, null, 2),
    ContentType: "application/json"
  }));
  return key;
}

/**
 * Delete a JSON item from S3 by id.
 */
async function deleteJsonItem(bucket, prefix, id) {
  const key = `${prefix}/${id}.json`;
  const { DeleteObjectCommand } = require("@aws-sdk/client-s3");
  await s3.send(new DeleteObjectCommand({ Bucket: bucket, Key: key }));
  return key;
}

async function copyPublicSettingsToUser(bucket, userPrefix) {
  const publicPrefix = "public/settings/";
  const publicKeys = await listAllObjects(bucket, publicPrefix);
  if (!publicKeys.length) return false;
  for (const key of publicKeys) {
    if (key.endsWith("/")) continue;
    const relative = key.slice(publicPrefix.length);
    const destKey = `${userPrefix}settings/${relative}`;
    const copySource = `${bucket}/${encodeURI(key)}`;
    await s3.send(new CopyObjectCommand({
      Bucket: bucket,
      CopySource: copySource,
      Key: destKey
    }));
  }
  return true;
}

async function loadUserSettings(bucket, settingsKey) {
  const res = await s3.send(new GetObjectCommand({ Bucket: bucket, Key: settingsKey }));
  const raw = await streamToString(res.Body);
  try {
    return raw ? JSON.parse(raw) : {};
  } catch (err) {
    return {};
  }
}

function isAbsolutePathLike(p) {
  if (!p) return false;
  const str = String(p);
  return /^[a-zA-Z]:[\\/]/.test(str) || str.startsWith("/") || str.startsWith("\\") || str.includes(":\\");
}

function normalizeSkillPathInput(pathInput) {
  if (!pathInput) return "";
  let raw = String(pathInput);
  raw = raw.replace(/^[a-zA-Z]:[\\/]/, ""); // drop drive prefix
  raw = raw.replace(/\\/g, "/");
  raw = raw.replace(/\.{2,}/g, "_");
  raw = raw.replace(/\s+/g, "_");
  raw = raw
    .split("/")
    .map((seg) => normalizePathSegment(seg).replace(/[^a-zA-Z0-9_-]/g, "_"))
    .filter(Boolean)
    .join("/");
  return raw;
}

function normalizeSkillName(name, fallback) {
  const cleaned = normalizePathSegment(name || "").replace(/\s+/g, "_");
  if (cleaned) return cleaned;
  return normalizePathSegment(fallback || "skill").replace(/\s+/g, "_");
}

function parseSourceFiles(source) {
  if (!source) return [];
  return String(source)
    .split(",")
    .map((s) => s.trim())
    .filter((s) => s.length > 0);
}

async function prepareSkillUploadTargets({ skill, ownerEmail }) {
  const userDir = normalizeEmailForPath(ownerEmail);
  const skillBase = normalizeSkillName(skill.name, skill.id);
  let pathPrefix = "";
  if (skill.path && !isAbsolutePathLike(skill.path)) {
    pathPrefix = normalizeSkillPathInput(skill.path);
  }
  const pathForDb = pathPrefix
    ? (pathPrefix.endsWith(`/${skillBase}`) || pathPrefix === skillBase ? pathPrefix : `${pathPrefix}/${skillBase}`)
    : skillBase;
  const root = `${userDir}/${pathForDb}`;

  const diagramDirRaw = skill.diagram?.dir;
  const hasDiagramDir = !!diagramDirRaw;
  const diagramDir = hasDiagramDir ? normalizePathSegment(diagramDirRaw) || "diagram_dir" : null;
  const codeDir = "code_dir";

  const dataMappingKey = `${root}/data_mapping.json`;

  // Ensure prefixes exist
  if (diagramDir) {
    await ensurePrefixExists(SKILL_BUCKET, `${root}/${diagramDir}`);
  }
  await ensurePrefixExists(SKILL_BUCKET, `${root}/${codeDir}`);

  const upload_urls = {
    diagram: {},
    code: [],
    data_mapping: {}
  };

  if (diagramDir) {
    const diagramJsonKey = `${root}/${diagramDir}/${skillBase}.json`;
    const diagramBundleKey = `${root}/${diagramDir}/${skillBase}_bundle.json`;
    upload_urls.diagram.json = {
      key: diagramJsonKey,
      url: await getSignedUrl(
        s3,
        new PutObjectCommand({ Bucket: SKILL_BUCKET, Key: diagramJsonKey }),
        { expiresIn: 900 }
      )
    };
    upload_urls.diagram.bundle = {
      key: diagramBundleKey,
      url: await getSignedUrl(
        s3,
        new PutObjectCommand({ Bucket: SKILL_BUCKET, Key: diagramBundleKey }),
        { expiresIn: 900 }
      )
    };
  }

  upload_urls.data_mapping = {
    key: dataMappingKey,
    url: await getSignedUrl(
      s3,
      new PutObjectCommand({ Bucket: SKILL_BUCKET, Key: dataMappingKey }),
      { expiresIn: 900 }
    )
  };

  const sourceFiles = parseSourceFiles(skill.source);
  if (sourceFiles.length) {
    // Ensure code dir prefix exists (already ensured above)
    for (const file of sourceFiles) {
      const safeFile = normalizePathSegment(file) || file;
      const codeKey = `${root}/${codeDir}/${safeFile}`;
      const url = await getSignedUrl(
        s3,
        new PutObjectCommand({ Bucket: SKILL_BUCKET, Key: codeKey }),
        { expiresIn: 900 }
      );
      upload_urls.code.push({ key: codeKey, file: file, url });
    }
  }

  return { upload_urls, root, pathForDb, diagramDir, codeDir, dataMappingKey };
}
              
var api_caller = "anyone";



const range = (start, end, length = end - start + 1) =>
  Array.from({ length }, (_, i) => start + i);
  
function getFuncName() {
    return getFuncName.caller.name;
}
  
function days2ms(days) {
  return (days*24*3600*1000);
}

function mysleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}


function getRandomIntMax(max) {
  return Math.floor(Math.random() * max);
}

function getRandomIntMinMax(min, max) {
  min = Math.ceil(min);
  max = Math.floor(max);
  return Math.floor(Math.random() * (max - min) + min); //The maximum is exclusive and the minimum is inclusive
}



function rdsExecute(params) {
  var cmd = new ExecuteStatementCommand(params);
  return new Promise((resolve, reject) => {
    util.log("DEBUG", "inside promise", api_caller, "rdsExecute", logFlag);
    
    RDS.send(cmd, (err, data) => {
      if (err) {
          util.log("Error executing MySQL statement: ", JSON.stringify(err), api_caller, "rdsExecute", logFlag);
          errMsg = JSON.stringify(err);
          reject(Error("MySQL statement error"));
      } else {
          util.log("Successfully executed a MySQL statement:", JSON.stringify(data), api_caller, "rdsExecute", logFlag);
          resolve(data);
      }
    });
  });
}



function rdsBatchExecute(params) {
  return new Promise((resolve, reject) => {
    util.log("DEBUG", "rds batch execute....", api_caller, "rdsBatchExecute", logFlag);
    RDS.batchExecuteStatement(params, (err, data) => {
      if (err) {
          util.log("Error batch executing MySQL statement: ", JSON.stringify(err), api_caller, "rdsBatchExecute", logFlag);
          errMsg = JSON.stringify(err);
          reject(Error("MySQL statement error"));
      } else {
          util.log("Successfully batch executed a MySQL statement:", JSON.stringify(data), api_caller, "rdsBatchExecute", logFlag);
          resolve(data);
      }
    });
  });
}




function createNewAgentsStatement(agentData, logFlag) {
  var i, j;
  util.log("DEBUG", 'creating insert bots statements---------------------------------->', api_caller, "createNewBotsStatement", logFlag);
  var insertAgentsStatement = "INSERT INTO AGENTS VALUES ";

  if (agentData.length > 0) {
    for (i = 0; i < agentData.length ; i++) {
      insertAgentsStatement = insertAgentsStatement + "( ";
      insertAgentsStatement = insertAgentsStatement + "NULL, " + "\'" + agentData[i].owner + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].gender + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].organizations + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].rank + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].supervisors + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].subordinates + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].title + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].personalities + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].birthday + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].name + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].status + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].metadata + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].vehicle + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].skills + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].tasks + "\', ";
      insertAgentsStatement = insertAgentsStatement + "\'" + agentData[i].knowledges + "\' ";

      insertAgentsStatement = insertAgentsStatement + ")";
      if (i != agentData.length-1) {
        insertAgentsStatement = insertAgentsStatement + ", ";
      } else {
        insertAgentsStatement = insertAgentsStatement + ";";
      }
    }
  }
  util.log("DEBUG", insertAgentsStatement, api_caller, "createNewAgentsStatement", logFlag);
  return insertAgentsStatement;
}

// TODO: do we really want to delete from the DB? (or just mark them as done, maybe keep a 12 month grace period)
// should we delete the agents associated with the agid s as well?
function createRemoveAgentsStatement(deleteData, logFlag) {
  var i;
  util.log("DEBUG", 'deleting agents from the agents db ---------------------------------->' + JSON.stringify(deleteData), api_caller, "createRemoveAgentsStatement", logFlag);
  var removeAgentsStatement = "DELETE FROM AGENTS WHERE agid IN ( ";
  if (deleteData.length > 0) {
    for (i = 0; i < deleteData.length ; i++) {
      util.log("DEBUG", 'deleteData-->' +i.toString() +" "+JSON.stringify(deleteData[i]), api_caller, "createRemoveAgentsStatement", logFlag);

      removeAgentsStatement = removeAgentsStatement + deleteData[i].oid;
      if (i != deleteData.length-1) {
        removeAgentsStatement = removeAgentsStatement + ", ";
      } else {
        removeAgentsStatement = removeAgentsStatement + "";
      }
    }
    removeAgentsStatement = removeAgentsStatement + ");";
  }

  util.log("DEBUG", removeAgentsStatement, api_caller, "createRemoveAgentsStatement", logFlag);
  return removeAgentsStatement;
}


// botid, owner, levels, walk30, walk90, walk365, buy30, buy90, buy365, gdFB30, gdFB90, gdFB365, gdRV30, gdRV90, gdRV365, bdFB30, bdFB90, bdFB365
// lastWalk, lastBuy, lastGoodFB, lastRVFB, lastBadFB, interests, location
// botid, owner, levels, levelStart, birthday, interests, location, roles
function createUpdateAgentsStatement(agentData, pplIds, logFlag) {
  var i, j, pid;
  util.log("DEBUG", 'creating update agents statements---------------------------------->', api_caller, "createUpdateAgentsStatement", logFlag);
  var updateAgentsStatement = "";

  if (agentData.length > 0) {
    for (i = 0; i < agentData.length ; i++) {
      updateAgentsStatement = updateAgentsStatement + "UPDATE AGENTS SET ";
      updateAgentsStatement = updateAgentsStatement + "gender = "  + "\'" + agentData[i].gender + "\', ";
      updateAgentsStatement = updateAgentsStatement + "organizations = "  + "\'" + agentData[i].organizations + "\', "; 
      updateAgentsStatement = updateAgentsStatement + "rank = "  + "\'" + agentData[i].rank + "\', "; 
      updateAgentsStatement = updateAgentsStatement + "supervisors = "  + "\'" + agentData[i].supervisors + "\', ";
      updateAgentsStatement = updateAgentsStatement + "title = "  + "\'" + agentData[i].title + "\', "; 
      updateAgentsStatement = updateAgentsStatement + "personalities = "  + "\'" + agentData[i].personalities + "\', "; 
      updateAgentsStatement = updateAgentsStatement + "birthday = "  + "\'" + agentData[i].birthday + "\', "; 
      updateAgentsStatement = updateAgentsStatement + "name = "  + "\'" + agentData[i].name + "\', "; 
      updateAgentsStatement = updateAgentsStatement + "`status` = "  + "\'" + agentData[i].status + "\', "; 
      updateAgentsStatement = updateAgentsStatement + "metadata = "  + "\'" + agentData[i].metadata + "\', "; 
      updateAgentsStatement = updateAgentsStatement + "vehicle = "  + "\'" + agentData[i].vehicle + "\', "; 
      updateAgentsStatement = updateAgentsStatement + "skills = "  + "\'" + agentData[i].skills + "\', "; 
      updateAgentsStatement = updateAgentsStatement + "skills = "  + "\'" + agentData[i].tasks + "\', "; 
      updateAgentsStatement = updateAgentsStatement + "knowledges = "  + "\'" + agentData[i].knowledges + "\' "; 
      updateAgentsStatement = updateAgentsStatement + "WHERE agid = " + agentData[i].agid;
      updateAgentsStatement = updateAgentsStatement + ";";
    }
  }
  util.log("DEBUG", updateAgentsStatement, api_caller, "createUpdateAgentsStatement", logFlag);
  return updateAgentsStatement;
}




// query bots by owner, platform, app, site, name
function createQueryAgentsStatement(qsettings, owner, callback, logFlag) {
  var i, j, pid;
  util.log("DEBUG", 'creating query agents statements---------------------------------->', api_caller, "createQueryAgentsStatement", logFlag);
  

  var queryAgentsStatement = "SELECT * FROM AGENTS WHERE ";
  if (qsettings["byowneruser"]) {
    queryAgentsStatement = queryAgentsStatement + "( owner = \'" + owner + "\');";
  } else {
    let qwords = qsettings["qphrase"].trim().replace(/([ .,;]+)/g,'|');
    
    queryAgentsStatement = queryAgentsStatement + "(( owner = \'" + owner + "\') AND ";

    queryAgentsStatement = queryAgentsStatement + "( levels RLIKE \'" + qwords + "\' OR ";
    queryAgentsStatement = queryAgentsStatement + " interests RLIKE \'" + qwords + "\' OR ";
    queryAgentsStatement = queryAgentsStatement + " status RLIKE \'" + qwords + "\' OR ";
    queryAgentsStatement = queryAgentsStatement + " location RLIKE \'" + qwords + "\' OR ";
    queryAgentsStatement = queryAgentsStatement + " gender RLIKE \'" + qwords + "\' ));";

  }
  

  util.log("DEBUG", queryAgentsStatement, api_caller, "createQueryAgentsStatement", logFlag);
  return queryAgentsStatement;
}



function createQueryAgentsOnVehiclesStatement(vnames_string, callback, logFlag) {
  
  var queryAgentsStatement = `SELECT * FROM AGENTS WHERE vehicle IN (${vnames_string})`;
  
  util.log("DEBUG", queryAgentsStatement, api_caller, "createQueryAgentsOnVehiclesStatement", logFlag);
  return queryAgentsStatement;
}



function createQueryAfterAddAgentsStatement(agentData, callback, logFlag) {
  var i, j, pid;
  util.log("DEBUG", 'creating query agents statements after add ------------------>', api_caller, "createQueryAfterAddAgentsStatement", logFlag);
  
  if (agentData.length > 0) {
    var queryAgentsStatement = "SELECT * FROM AGENTS WHERE ";
    for (i = 0; i < agentData.length ; i++) {
      queryAgentsStatement = queryBotsStatement + "( owner = \'" + agentData[i].owner + "\' AND";
      queryAgentsStatement = queryBotsStatement + " levelStart = \'" + agentData[i].levelStart + "\' AND ";
      queryAgentsStatement = queryBotsStatement + " gender = \'" + agentData[i].gender + "\' AND ";
      queryAgentsStatement = queryBotsStatement + " location = \'" + agentData[i].location + "\' AND ";
      queryAgentsStatement = queryBotsStatement + " birthday = \'" + agentData[i].birthday + "\' AND ";
      queryAgentsStatement = queryBotsStatement + " interests = \'" + agentData[i].interests + "\' ) ";
      if (i != agentData.length-1) {
        queryAgentsStatement = queryAgentsStatement + " OR ";
      } else {
        queryAgentsStatement = queryAgentsStatement + ";";
      }
    }
  }
  util.log("DEBUG", queryAgentsStatement, api_caller, "createQueryAfterAddAgentsStatement", logFlag);
  return queryAgentsStatement;
}



//-------------------------- agents related DB processing---------------------------------------------------

const agent_template = {
  agid : 0,
  owner : "",
  gender : "m",
  organizations : "",
  rank : "",
  supervisors : "",
  subordinates : "",
  title : "",
  personalities: "",
  birthday : "2000-01-01",
  name: "",
  status : "",
  metadata : {},
  vehicle: "",
  skills: "",
  tasks: "",
  knowledges : ""
};

function coerceJsonObject(value, fallback = {}) {
  if (!value) {
    return { ...fallback };
  }
  if (typeof value === "string") {
    try {
      return { ...JSON.parse(value) };
    } catch (err) {
      return { ...fallback };
    }
  }
  if (typeof value === "object") {
    return { ...value };
  }
  return { ...fallback };
}

async function hydrateSkillAssets(skillInput, owner, existingSkill = null, options = {}) {
  const { allowCloudSync = true } = options;
  const baseSkill = { ...skillInput };
  const descriptor = {
    path: baseSkill.path || existingSkill?.path,
    name: baseSkill.name || existingSkill?.name,
    id: baseSkill.id || existingSkill?.id
  };
  let manifest;
  try {
    manifest = await skillAssetService.buildManifest(owner, descriptor);
  } catch (err) {
    return { skill: baseSkill, error: err };
  }
  if (!manifest) {
    return { skill: baseSkill };
  }
  if (manifest.relativePaths.length) {
    baseSkill.path = manifest.relativeSkillPath || baseSkill.path;
    const config = coerceJsonObject(baseSkill.config);
    config.asset_manifest = {
      bucket: manifest.bucket,
      prefix: manifest.prefix,
      files: manifest.relativePaths
    };
    baseSkill.config = config;
    if (allowCloudSync) {
      try {
        await skillAssetService.syncManifestWithCloud({
          owner,
          skillId: baseSkill.id || descriptor.id,
          skillName: baseSkill.name || descriptor.name,
          manifest
        });
      } catch (syncError) {
        return { skill: baseSkill, warning: syncError.message };
      }
    }
  }
  return { skill: baseSkill };
}

//data format conversion from mysql db records type to the desired data structure type.
function convertAgentRecords(agentrecords) {
  console.log("botrecords:", JSON.stringify(agentrecords));
    var agentds = [];
    var agentd;
    var i = 0;
    for (var agentrec of agentrecords.records) {
        i = 0;
        agentd = Object.create(agent_template);
        agentd.agid = agentrec[i++]['longValue'];
        agentd.owner = agentrec[i++]['stringValue'];
        agentd.gender = agentrec[i++]['stringValue'];
        agentd.organizations = agentrec[i++]['stringValue'];
        agentd.rank = agentrec[i++]['stringValue'];
        agentd.supervisors = agentrec[i++]['stringValue'];
        agentd.subordinates = agentrec[i++]['stringValue'];
        agentd.title = agentrec[i++]['stringValue'];
        agentd.personalities = agentrec[i++]['stringValue'];
        agentd.birthday = agentrec[i++]['stringValue'];
        agentd.name = agentrec[i++]['stringValue'];
        agentd.status = agentrec[i++]['stringValue'];
        agentd.metadata = JSON.parse(agentrec[i++]['stringValue']);
        agentd.vehicle = agentrec[i++]['stringValue'];
        agentd.skills = agentrec[i++]['stringValue'];
        agentd.tasks = agentrec[i++]['stringValue'];
        agentd.knowledges = agentrec[i++]['stringValue'];
        agentds.push(agentd);
    }

  return agentds;
}



// the main purpose is find the just-added missions and get their mission IDs.
function queryAgentsAfterAdd(inData, callback, logFlag, test_stub) {
  var qAgentsString;
  var n = inData.length;

  var lastKey = 0;
  var sqlStatement = "SELECT MAX(mid) FROM AGENTS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };

	if ((!test_stub["testmode"]) || (test_stub["testmode"] && !test_stub['skip_queryAgentsAfterAdd'])) {
        if (inData.length > 0) {
          qAgentsString = createQueryAfterAddAgentsStatement(inData, callback, logFlag);
          util.log("DEBUG", "query agents after add...." + qAgentsString);
          params.sql = qAgentsString;
          return rdsExecute(params)
          .catch (error => {
              errMsg = JSON.stringify(error.message);
              err(99, error.message, callback);
          });
        } else {
            return Promise.resolve(null);
        }
    } else {
      if (test_stub['passThruGenID_queryAgentsAfterAdd']) {

        let qmRecs = fakeQueryAgents(inData);

        util.log("DEBUG", "query bots....fake pass thru:" + JSON.stringify(qmRecs), api_caller, "queryAgentsAfterAdd", logFlag);

        return Promise.resolve(qmRecs);
      } else {
        return Promise.resolve(test_stub["queryAgentsAfterAdd"]);
      }
    }
}


function addAgents(inData, callback, logFlag, test_stub) {
  var newAgentsString;
  var n = inData.length;

  var lastKey = 0;
  var sqlStatement = "SELECT MAX(botid) FROM AGENTS";
  var newStartRow = 0;
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };
  
  util.log("DEBUG", "add new agents....", api_caller, "addAgents", logFlag);

  newAgentsString = createNewAgentsStatement(inData, logFlag);
  params.sql = newAgentsString;
  return rdsExecute(params)
  .then(res => {
    return queryAgentsAfterAdd(inData, callback, logFlag, test_stub);
	})
	.then(agrecs => {
    if (agrecs["records"].length == inData.length) {
        var addedagents = convertAgentRecords(agrecs);
        return Promise.resolve(addedagents);
    } else {
      util.log("ERROR: ", "add agents not fully successfull ....", api_caller, "addAgents", logFlag);
      err(97, "# of agents added not matching input", callback);
    }
    
  })
  .catch (error => {
    util.log("ERROR: ", "add agents failed....", api_caller, "addAgents", logFlag);
    errMsg = JSON.stringify(error.message);
    err(99, error.message, callback);
  });
}



function removeAgents(inData, callback, logFlag, test_stub) {
  var removeAgentsString;
  var n = inData.length;

  var lastKey = 0;
  var sqlStatement = "SELECT MAX(PID) FROM AGENTS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };
  
  util.log("DEBUG", "remove agents....", api_caller, "removeAgents", logFlag);

  removeAgentsString = createRemoveAgentsStatement(inData, logFlag);
  params.sql = removeAgentsString;
  return rdsExecute(params)
  .catch (error => {
      errMsg = JSON.stringify(error.message);
      err(99, error.message, callback);
  });
}




function updateAgents(inData, bots2bu, callback, logFlag, test_stub) {
  const chunkSize = 16; // Define the chunk size for batch processing
  const Secrets = "arn:aws:secretsmanager:us-east-1:667118410653:secret:rds-db-credentials/cluster-3PWC5NJ26SWUSO74X5PDRLYS5Q/admin-6Oqidf";
  const Cluster = "arn:aws:rds:us-east-1:667118410653:cluster:ppl";
  const DB = "TPSMirror";

  // Process a single chunk of data
  function processChunk(chunk) {
    let numberOfRecordsUpdated = 0;

    return getAgentsByIds(chunk.map(a => a.agid), callback, logFlag, test_stub)
      .then(data => {
        util.log("DEBUG", JSON.stringify(data), api_caller, "updateAgents", logFlag);
        let dbrecs = data.records;

        if (dbrecs.length > 0) {
          for (let r of dbrecs) {
            let found = chunk.find(element => element.agid == r[0]["longValue"]);
            if (found) {
              found.levelStart = r[3]["stringValue"];
              found.delDate = r[10]["stringValue"];
            }
          }
        }

        // Generate individual update statements for each bot
        const updateStatements = chunk.map(agent => createUpdateAgentsStatement([agent], logFlag));

        // Sequentially execute each statement
        return updateStatements.reduce((promiseChain, statement) => {
          const params = {
            secretArn: Secrets,
            resourceArn: Cluster,
            sql: statement,
            database: DB,
          };

          util.log("DEBUG", "Executing update: " + statement, api_caller, "updateAgents", logFlag);

          return promiseChain
            .then(() => rdsExecute(params))
            .then(() => {
              numberOfRecordsUpdated++; // Increment the counter on successful execution
            });
        }, Promise.resolve());
      })
      .then(() => {
        // Return the emulated result for this chunk
        const result = { numberOfRecordsUpdated };
        util.log("DEBUG", "Chunk result: " + JSON.stringify(result), api_caller, "updateAgents", logFlag);
        return result;
      })
      .catch(error => {
        util.log("ERROR", "Error processing chunk: " + error.message, api_caller, "updateAgents", logFlag);
        throw error; // Let the caller handle the error
      });
  }

  
// Split input data into chunks and process each chunk sequentially
function processAllChunks(data) {
  const chunks = [];
  for (let i = 0; i < data.length; i += chunkSize) {
    chunks.push(data.slice(i, i + chunkSize));
  }

  let totalRecordsUpdated = 0;

  return chunks.reduce((promiseChain, chunk) => {
    return promiseChain
      .then(() => processChunk(chunk))
      .then(result => {
        totalRecordsUpdated += result.numberOfRecordsUpdated;
      });
  }, Promise.resolve()).then(() => {
    return { numberOfRecordsUpdated: totalRecordsUpdated };
  });
}


  // Main logic
  util.log("DEBUG", "Updating bots...", api_caller, "updateAgents", logFlag);

  return processAllChunks(inData)
    .then(result => {
      util.log("DEBUG", "Final result: " + JSON.stringify(result), api_caller, "updateAgents", logFlag);
      callback(null, result);
    })
    .catch(error => {
      util.log("ERROR", "Error in updateAgents: " + error.message, api_caller, "updateAgents", logFlag);
      callback(error, null);
    });
}

// this function fetches all bots under the input owner
// assume: ids.length > 0
function getAgentsByIds(ids, callback, logFlag, test_stub) {
  var i;
  var sqlStatement = "SELECT * FROM AGENTS WHERE agid in ( " ;
  util.log("DEBUG", "TESTSTUB: " +JSON.stringify(ids) + ":::"+JSON.stringify(test_stub), api_caller, "getAgentsByIds", logFlag);
  
  if ((!test_stub["testmode"]) || (test_stub["testmode"] && !test_stub['skip_getBotsByIds'])) {
    
    if (ids.length > 0) {
  
      for(i=0; i < ids.length-1 ; i++) {
        sqlStatement = sqlStatement + ids[i] + ", ";
      }
      sqlStatement = sqlStatement + ids[i];
      
      
      sqlStatement = sqlStatement + " );";
      util.log("DEBUG", "get agent ids statement: " + sqlStatement, api_caller, "getAgentsByIds", logFlag);
      const params = {
        secretArn: Secrets,  
        resourceArn: Cluster, 
        sql: sqlStatement,
        database: DB  
      };
      
      util.log("DEBUG", "get all agents with IDs ...."+sqlStatement , api_caller, "getAgentsByIds", logFlag);
    
      return rdsExecute(params)
      // ToDo: need another step here to update person's male/female by query male/female database using the first name.
      // need another step here to update person's ethnicy by query ethnicity last name table.
      .catch (error => {
        util.log("ERROR", "getAgentsByIds ....oh no", api_caller, "getAgentsByIds", logFlag);
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
      });
    } else {
      return Promise.resolve({records:[]});
    }
  } else {
    return Promise.resolve(test_stub['getAgentsByIds'])
  }
}


// this function fetches all bots under the input owner
function getAgents(owner, callback, logflag, test_stub) {
  
  var sqlStatement = "SELECT * FROM AGENTS WHERE (owner = \'" + owner + "\' OR owner = \'public\') and status = \'active\'" ;
  util.log("DEBUG", "getAgents sqlStatement: " + sqlStatement, api_caller, "getAgents", logFlag);
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };
  
  if ((!test_stub["testmode"]) || (test_stub["testmode"] && !test_stub['skip_getAgents'])){
  
    util.log("DEBUG", "get all agents under me ....", api_caller, "getAgents", logFlag);
  
    return rdsExecute(params)
    // ToDo: need another step here to update person's male/female by query male/female database using the first name.
    // need another step here to update person's ethnicy by query ethnicity last name table.
    .catch (error => {
        util.log("ERROR", "getAgents.....oh no....", api_caller, "getAgents", logFlag)
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
    });
  } else {
    util.log("DEBUG", "fake get all agents under me ...."+JSON.stringify(test_stub['getAgents']), api_caller, "getAgents", logFlag);
    return Promise.resolve(test_stub['getAgents'])
  }

}






function queryAgents(owner, inData, callback, logFlag, test_stub) {
  var qAgentsString;

  var sqlStatement = "SELECT MAX(mid) FROM AGENTS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };

  if (inData) {
    qAgentsString = createQueryAgentsStatement(inData, owner, logFlag);
    util.log("DEBUG", "query agents...." + qAgentsString, api_caller, "queryAgents", logFlag);
    params.sql = qAgentsString;
    return rdsExecute(params)
    .then(arecs => {
      console.log("query agents....");
      var foundAgents = convertBotRecords(arecs);

      return Promise.resolve(foundAgents);
    })
    .catch (error => {
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
    });
  } else {
    return Promise.resolve(null);
  }
}




function queryBotsOnVehicles(inData, callback, logFlag, test_stub) {
  var qBotsString;

  var sqlStatement = "SELECT MAX(mid) FROM MISSIONS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };

  if (inData) {
    qBotsString = createQueryBotsOnVehiclesStatement(inData, callback, logFlag);
    util.log("DEBUG", "query bots on vehicles...." + qBotsString, api_caller, "queryBotsOnVehicles", logFlag);
    params.sql = qBotsString;
    return rdsExecute(params)
    .then(brecs => {
      console.log("what bots....", JSON.stringify(brecs));
      
      var foundBots = convertBotRecords(brecs);

      return Promise.resolve(foundBots);
    })
    .catch (error => {
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
    });
  } else {
    return Promise.resolve(null);
  }
}





// now onto agent skills -------------------------------------------------------------------------------------------------------------------

function createNewAgentSkillsStatement(skillData, owner, callback, logFlag) {
  var i, j, skid;
  util.log("DEBUG", 'creating insert agent skills statements---------------------------------->', api_caller, "createNewAgentSkillsStatement", logFlag);
  var inserSkillssStatement = "INSERT INTO AGENT_SKILLS VALUES ";
  if (skillData.length > 0) {
    for (i = 0; i < skillData.length ; i++) {
      inserSkillssStatement = inserSkillssStatement + "( NULL, " + "\'" + owner + "\', ";
      inserSkillssStatement = inserSkillssStatement + "\'" + skillData[i].createdOn + "\', ";
      inserSkillssStatement = inserSkillssStatement + "\'" + skillData[i].platform + "\', ";
      inserSkillssStatement = inserSkillssStatement + "\'" + skillData[i].app + "\', ";
      inserSkillssStatement = inserSkillssStatement + "\'" + skillData[i].site_name + "\', ";
      inserSkillssStatement = inserSkillssStatement + "\'" + skillData[i].site + "\', ";
      inserSkillssStatement = inserSkillssStatement + "\'" + skillData[i].page + "\', ";
      inserSkillssStatement = inserSkillssStatement + "\'" + skillData[i].name + "\', ";
      inserSkillssStatement = inserSkillssStatement + "\'" + skillData[i].path + "\', ";
      inserSkillssStatement = inserSkillssStatement + "\'" + skillData[i].main + "\', ";
      inserSkillssStatement = inserSkillssStatement + "\'" + skillData[i].description + "\', ";
      inserSkillssStatement = inserSkillssStatement + "" + skillData[i].runtime + ", ";
      inserSkillssStatement = inserSkillssStatement + "\'" + skillData[i].price_model + "\', ";
      inserSkillssStatement = inserSkillssStatement + "" + skillData[i].price + ", ";
      
      inserSkillssStatement = inserSkillssStatement + "\'" + skillData[i].privacy + "\')";
      if (i != skillData.length-1) {
        inserSkillssStatement = inserSkillssStatement + ", ";
      } else {
        inserSkillssStatement = inserSkillssStatement + ";";
      }
    }
  }
  util.log("DEBUG", inserSkillssStatement, api_caller, "createNewAgentSkillsStatement", logFlag);
  return inserSkillssStatement;
}


function createRemoveAgentSkillsStatement(deleteData, logFlag) {
  var i;
  util.log("DEBUG", 'deleting from the agent skills db ------------------------->' + JSON.stringify(deleteData), api_caller, "createRemoveAgentSkillsStatement", logFlag);
  var removeSkillsStatement = "DELETE FROM AGENT_SKILLS WHERE askid IN ( ";
  if (deleteData.length > 0) {
    for (i = 0; i < deleteData.length ; i++) {
      removeSkillsStatement = removeSkillsStatement + deleteData[i].oid;
      if (i != deleteData.length-1) {
        removeSkillsStatement = removeSkillsStatement + ", ";
      } else {
        removeSkillsStatement = removeSkillsStatement + "";
      }
    }
    removeSkillsStatement = removeSkillsStatement + ");";
  }

  util.log("DEBUG", "remove skills sql statement: " + removeSkillsStatement, api_caller, "createRemoveAgentSkillsStatement", logFlag);
  return removeSkillsStatement;
}


function createUpdateAgentSkillsStatement(skillData, owner, logFlag) {
  var i, j;
  util.log("DEBUG", 'creating update agent skill db --------------------->' + JSON.stringify(skillData), api_caller, "createUpdateAgentSkillsStatement", logFlag);
  var updateSkillsStatement = "UPDATE AGENT_SKILLS SET ";
  if (skillData.length > 0) {
    for (i = 0; i < skillData.length ; i++) {
      updateSkillsStatement = updateSkillsStatement + "owner = " + "\'" + owner + "\', ";
      updateSkillsStatement = updateSkillsStatement + "createdOn = "  + "\'" + skillData[i].createdOn + "\', ";

      updateSkillsStatement = updateSkillsStatement + "platform = "  + "\'" + skillData[i].platform + "\', ";
      updateSkillsStatement = updateSkillsStatement + "app = "  + "\'" + skillData[i].app + "\', ";
      updateSkillsStatement = updateSkillsStatement + "site = "  + "\'" + skillData[i].site_name + "\', ";
      updateSkillsStatement = updateSkillsStatement + "site = "  + "\'" + skillData[i].site + "\', ";
      updateSkillsStatement = updateSkillsStatement + "page = "  + "\'" + skillData[i].page + "\', ";  
      updateSkillsStatement = updateSkillsStatement + "name = "  + "\'" + skillData[i].name + "\', "; 
      updateSkillsStatement = updateSkillsStatement + "path = "  + "\'" + skillData[i].path + "\', "; 
      updateSkillsStatement = updateSkillsStatement + "main = "  + "\'" + skillData[i].main + "\', "; 
      updateSkillsStatement = updateSkillsStatement + "description = "  + "\'" + skillData[i].description + "\', "; 

      updateSkillsStatement = updateSkillsStatement + "runtime = "  + "" + skillData[i].runtime + ", "; 
      updateSkillsStatement = updateSkillsStatement + "price_model = "  + "\'" + skillData[i].price_model + "\', "; 
      updateSkillsStatement = updateSkillsStatement + "price = "  + "" + skillData[i].price + ", ";
      
      updateSkillsStatement = updateSkillsStatement + "privacy = "  + "\'" + skillData[i].privacy + "\' "; 

      updateSkillsStatement = updateSkillsStatement + "WHERE askid = " + skillData[i].skid;
      updateSkillsStatement = updateSkillsStatement + ";";
    }
  }

  util.log("DEBUG", updateSkillsStatement, api_caller, "createUpdateSkillsStatement", logFlag);
  return updateSkillsStatement;
}


// query skill by owner, platform, app, site, name
function createQueryAgentSkillsStatement(qsettings, owner, callback, logFlag) {
  var i, j, pid;
  util.log("DEBUG", 'creating query agent skills statements---------------------------------->', api_caller, "createQueryAgentSkillsStatement", logFlag);
  

  var querySkillsStatement = "SELECT * FROM SKILLS WHERE ";
  if (qsettings["byowneruser"]) {
      querySkillsStatement = querySkillsStatement + "( owner = \'" + owner + "\' OR owner = \'dbadmin@maipps.com\' );";
  } else {
    let qwords = qsettings["qphrase"].trim().replace(/([ .,;]+)/g,'|');
    
    querySkillsStatement = querySkillsStatement + "( platform RLIKE \'" + qwords + "\' OR ";
    querySkillsStatement = querySkillsStatement + " app RLIKE \'" + qwords + "\' OR ";
    querySkillsStatement = querySkillsStatement + " site RLIKE \'" + qwords + "\' OR ";
    querySkillsStatement = querySkillsStatement + " name RLIKE \'" + qwords + "\' OR ";
    querySkillsStatement = querySkillsStatement + " description RLIKE \'" + qwords + "\' ); ";

  }
  

  util.log("DEBUG", querySkillsStatement, api_caller, "createQueryAgentSkillsStatement", logFlag);
  return querySkillsStatement;
}




function createQueryAfterAddAgentSkillsStatement(skillData, owner, callback, logFlag) {
  var i, j, pid;
  util.log("DEBUG", 'creating query skills statements---------------------------------->', api_caller, "createQueryAfterAddAgentSkillsStatement", logFlag);
  
  if (skillData.length > 0) {
    var querySkillsStatement = "SELECT * FROM SKILLS WHERE ";
    for (i = 0; i < skillData.length ; i++) {
      querySkillsStatement = querySkillsStatement + "( owner = \'" + owner + "\' AND";
      querySkillsStatement = querySkillsStatement + " name = \'" + skillData[i].name + "\' AND ";
      querySkillsStatement = querySkillsStatement + " platform = \'" + skillData[i].platform + "\' AND ";
      querySkillsStatement = querySkillsStatement + " app = \'" + skillData[i].app + "\' AND ";
      querySkillsStatement = querySkillsStatement + " site = \'" + skillData[i].site + "\' AND ";
      querySkillsStatement = querySkillsStatement + " page = \'" + skillData[i].page + "\' AND ";
      querySkillsStatement = querySkillsStatement + " description = \'" + skillData[i].description + "\' AND ";
      querySkillsStatement = querySkillsStatement + " createdOn = \'" + skillData[i].createdOn + "\' ) ";
      if (i != skillData.length-1) {
        querySkillsStatement = querySkillsStatement + " OR ";
      } else {
        querySkillsStatement = querySkillsStatement + ";";
      }
    }
  }
  util.log("DEBUG", querySkillsStatement, api_caller, "createQueryAfterAddAgentSkillsStatement", logFlag);
  return querySkillsStatement;
}



const agent_skill_template = {
  askid : 0,
  owner : "",
  name : "",
  description : "",
  status : "inactive",
  path : "",
  flowgram: {},
  langgraph: {},
  config: {},
  price : 0.0
};

function convertAgentSkillRecord(skrec) {
  var skd;

  var i = 0;
  skd = Object.create(agent_skill_template);
  skd.askid = skrec[i++]['longValue'];
  skd.owner = skrec[i++]['stringValue'];
  skd.name = skrec[i++]['stringValue'];
  skd.description = skrec[i++]['stringValue'];
  skd.status = skrec[i++]['stringValue'];
  skd.path = skrec[i++]['stringValue'];
  skd.flowgram = JSON.parse(skrec[i++]['stringValue']);
  skd.langgraph = JSON.parse(skrec[i++]['stringValue']);
  skd.config = JSON.parse(skrec[i++]['stringValue']);
  skd.price = skrec[i++]['longValue'];
    
  return skd;
}


//data format conversion from mysql db records type to the desired data structure type.
function convertAgentSkillRecords(skillrecords) {
  var skills = [];
  var skd;

  var i = 0;
  for (var skrec of skillrecords.records) {
    i = 0;
    skd = Object.create(agent_skill_template);
    skd.skid = skrec[i++]['longValue'];
    skd.owner = skrec[i++]['stringValue'];
    skd.createdOn = skrec[i++]['stringValue'];
    skd.platform = skrec[i++]['stringValue'];
    skd.app = skrec[i++]['stringValue'];
    skd.site_name = skrec[i++]['stringValue'];
    skd.site = skrec[i++]['stringValue'];
    skd.page = skrec[i++]['stringValue'];
    skd.name = skrec[i++]['stringValue'];
    skd.path = skrec[i++]['stringValue'];
    skd.main = skrec[i++]['stringValue'];
    skd.description = skrec[i++]['stringValue'];
    skd.runtime = skrec[i++]['longValue'];
    skd.price_model = skrec[i++]['stringValue'];
    skd.price = skrec[i++]['longValue'];
    skd.privacy = skrec[i++]['stringValue'];
    
    skills.push(skd);
  }
  return skills;
}



function addSkills(inData, owner, callback, logFlag, test_stub) {
  var newSkillsString;
  var n = inData.length;

  var lastKey = 0;
  var sqlStatement = "SELECT MAX(mid) FROM MISSIONS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };

  if (inData.length > 0) {
    newSkillsString = createNewSkillsStatement(inData, owner, logFlag);
    util.log("DEBUG", "add new skills...." + newSkillsString, api_caller, "addSkills", logFlag);
    params.sql = newSkillsString;
    return rdsExecute(params)
    .then(res => {
        return querySkillsAfterAdd(inData, owner, callback, logFlag, test_stub);
	  })
	  .then(skrecs => {
	    if (skrecs["records"].length > 0) {
	      util.log("DEBUG", "read back skill records...." + JSON.stringify(skrecs), api_caller, "addSkills", logFlag);
  	    if (skrecs["records"].length == inData.length) {
  	      var addedSkills = convertSkillRecords(skrecs);
  	      return Promise.resolve(addedSkills);
  	      
  	    } else {
  	      var addedSkills = convertSkillRecords(skrecs);
          util.log("ERROR: ", "add skills not fully successfull ....", api_caller, "addSkills", logFlag);
          // err(97, "# of skills added not matching input", callback);
          return Promise.resolve([addedSkills[addedSkills.length-1]])
        }
	    } else {
	      err(97, "# of skills added is 0", callback);
	    }
      
    })
    .catch (error => {
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
    });
  } else {
    return Promise.resolve(null);
  }
}



function removeSkills(inData, callback, logFlag, test_stub) {
  var removeSkillsString;
  var n = inData.length;

  var lastKey = 0;
  var sqlStatement = "SELECT MAX(PID) FROM BOTS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };
  
  util.log("DEBUG", "remove skills....", api_caller, "removeSkills", logFlag);

  removeSkillsString = createRemoveSkillsStatement(inData, logFlag);
  params.sql = removeSkillsString;
  return rdsExecute(params)
  .catch (error => {
      errMsg = JSON.stringify(error.message);
      err(99, error.message, callback);
  });
}



function merge_skill_data(existing_skill_data, incoming_skill_data) {
  // note: skid, createdOn should never be updated....
  existing_skill_data.platform = incoming_skill_data.platform;
  existing_skill_data.app = incoming_skill_data.app;
  existing_skill_data.site_name = incoming_skill_data.site_name;
  existing_skill_data.site = incoming_skill_data.site;
  existing_skill_data.name = incoming_skill_data.name;
  existing_skill_data.path = incoming_skill_data.path;
  existing_skill_data.runtime = incoming_skill_data.runtime;
  existing_skill_data.price_model = incoming_skill_data.price_model;
  existing_skill_data.price = incoming_skill_data.price;      
  existing_skill_data.description = incoming_skill_data.description;
  existing_skill_data.privacy = incoming_skill_data.privacy;
    
  return existing_skill_data;
}

function updateSkills(inData, owner, callback, logFlag, test_stub) {
  var updateSkillsString;
  var skids = inData.map(function(a) {return a.skid;});
  var skdata = [];
  var found;

  var sqlStatement = "SELECT MAX(PID) FROM BOTS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };
  
  util.log("DEBUG", "updating skills....", api_caller, "updateSkills", logFlag);
  
  return getSkillsByIds(skids, callback, test_stub)
  .then(data => {
    let dbrecs = data.records;
    util.log("skills DBRECS: " + JSON.stringify(dbrecs), api_caller, "updateSkills", logFlag);

    if (dbrecs.length > 0) {
      for (var r of dbrecs) {
        found = inData.find(element => element.skid == r[0]["longValue"]);

        skdata.push(merge_skill_data(convertSkillRecord(r), found));
      }
    }
    
    updateSkillsString = createUpdateSkillsStatement(skdata, owner, logFlag);
    params.sql = updateSkillsString;

    return rdsExecute(params)
  })
  .catch (error => {
      errMsg = JSON.stringify(error.message);
      err(99, error.message, callback);
  });
}


//get all public skills and skills owned by this user
function getAgentSkills(owner, callback, test_stub) {
  var i;
  var sqlStatement = "SELECT * FROM AGENT_SKILLS WHERE owner='"+owner+"' OR owner='public';" ;
  util.log("DEBUG", "TESTSTUB: " + JSON.stringify(test_stub), api_caller, "getAgentSkills", logFlag);
  
  if ((!test_stub["testmode"]) || (test_stub["testmode"] && !test_stub['skip_getAgentSkills'])) {


    util.log("DEBUG", "get agent skills statement: " + sqlStatement, api_caller, "getAgentSkills", logFlag);
    const params = {
      secretArn: Secrets,  
      resourceArn: Cluster, 
      sql: sqlStatement,
      database: DB  
    };
    
    util.log("DEBUG", "get all pub and my agent skills ....", api_caller, "getAgentSkills", logFlag);
  
    return rdsExecute(params)
    // ToDo: need another step here to update person's male/female by query male/female database using the first name.
    // need another step here to update person's ethnicy by query ethnicity last name table.
    .catch (error => {
      util.log("ERROR", "get agent skills ....oh no", api_caller, "getAgentSkills", logFlag);
      errMsg = JSON.stringify(error.message);
      err(99, error.message, callback);
    });

  } else {
    return Promise.resolve(test_stub['getAgentSkills'])
  }
}



function getAgentSkillsByIds(ids, callback, test_stub) {
  var i;
  var sqlStatement = "SELECT * FROM AGENT_SKILLS WHERE askid in ( " ;
  util.log("DEBUG", "TESTSTUB: " + JSON.stringify(test_stub), api_caller, "getAgentSkillsByIds", logFlag);
  
  if ((!test_stub["testmode"]) || (test_stub["testmode"] && !test_stub['skip_getAgentSkillsByIds'])) {
    
    if (ids.length > 0) {
  
      for(i=0; i < ids.length-1 ; i++) {
        sqlStatement = sqlStatement + ids[i] + ", ";
      }
      sqlStatement = sqlStatement + ids[i];
      
      
      sqlStatement = sqlStatement + " );";
      util.log("DEBUG", "get ids statement: " + sqlStatement, api_caller, "getAgentSkillsByIds", logFlag);
      const params = {
        secretArn: Secrets,  
        resourceArn: Cluster, 
        sql: sqlStatement,
        database: DB  
      };
      
      util.log("DEBUG", "get all agent skills with IDs ....", api_caller, "getAgentSkillsByIds", logFlag);
    
      return rdsExecute(params)
      // ToDo: need another step here to update person's male/female by query male/female database using the first name.
      // need another step here to update person's ethnicy by query ethnicity last name table.
      .catch (error => {
        util.log("ERROR", "getAgentSkillsByIds ....oh no", api_caller, "getSkillsgetAgentSkillsByIdsByIds", logFlag);
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
      });
    } else {
      return Promise.resolve([]);
    }
  } else {
    return Promise.resolve(test_stub['getAgentSkillsByIds'])
  }
}





function queryAgentSkills(owner, inData, callback, logFlag, test_stub) {
  var qSkillsString;

  var sqlStatement = "SELECT MAX(mid) FROM AGENT_SKILLS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };

  if (inData) {
    qSkillsString = createQueryAgentSkillsStatement(inData, owner, logFlag);
    util.log("DEBUG", "query agent skills...." + qSkillsString, api_caller, "queryAgentSkills", logFlag);
    params.sql = qSkillsString;
    return rdsExecute(params)
    .then(skrecs => {
      var foundSkills = convertAgentSkillRecords(skrecs);
      return Promise.resolve(JSON.stringify(foundSkills));
    })
    .catch (error => {
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
    });
  } else {
    return Promise.resolve(null);
  }
}



// now onto agent tasks -------------------------------------------------------------------------------------------------------------------
function createNewAgentTasksStatement(tasksData, callback, logFlag) {
  var i, j, pid;
  var config_string;
  util.log("DEBUG", 'creating insert agent tasks statements---------------------------------->', api_caller, "createNewAgentTasksStatement", logFlag);
  console.log("in mission data:", JSON.stringify(tasksData));
  var inserAgentTasksStatement = "INSERT INTO AGENT_TASKS VALUES ";
  if (tasksData.length > 0) {
    // for (i = 0; i < tasksData.length ; i++) {
    const last_idx = tasksData.length;
    for (i = 0; i < last_idx ; i++) {
      inserAgentTasksStatement = inserAgentTasksStatement + "( NULL, ";
      inserAgentTasksStatement = inserAgentTasksStatement + "" + tasksData[i].ticket.toString() + ", ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].owner + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "" + tasksData[i].botid.toString() + ", ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].status + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].createon + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].esd + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].ecd + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].asd + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].abd + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].aad + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].afd + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].acd + "\', ";
      
      inserAgentTasksStatement = inserAgentTasksStatement + "" + tasksData[i].esttime.toString() + ", ";
      inserAgentTasksStatement = inserAgentTasksStatement + "" + tasksData[i].runtime.toString() + ", ";

      inserAgentTasksStatement = inserAgentTasksStatement + "" + tasksData[i].trepeat.toString() + ", ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].cuspas + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].category + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].phrase + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].pseudoStore + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].pseudoBrand + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].pseudoASIN + "\', ";

      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].type + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "" + tasksData[i].as_server + ", ";
      if (typeof tasksData[i].config === 'string') {
      // if (tasksData[i].config === '{}') {
        config_string = tasksData[i].config;
      } else {
        config_string = JSON.stringify(tasksData[i].config).replace(/'/g, "\\'");
      }
      
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + config_string + "\', ";

      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].skills + "\', ";
      inserAgentTasksStatement = inserAgentTasksStatement + "\'" + tasksData[i].delDate + "\')";
      if (i != last_idx-1) {
        inserAgentTasksStatement = inserAgentTasksStatement + ", ";
      } else {
        inserAgentTasksStatement = inserAgentTasksStatement + ";";
      }
    }
  }
  util.log("DEBUG", inserAgentTasksStatement, api_caller, "createNewAgentTasksStatement", logFlag);
  return inserAgentTasksStatement;
}




// TODO: do we really want to delete from the DB? (or just mark them as deleted, maybe keep a 12 month grace period)
// 
function createRemoveAgentTasksStatement(deleteData, logFlag) {
  var i;
  util.log("DEBUG", 'deleting from the agent tasks db -------------->' + JSON.stringify(deleteData), api_caller, "createRemoveAgentTasksStatement", logFlag);
  var removeAgentTasksStatement = "DELETE FROM AGENT_TASKS WHERE ataskid IN ( ";
  if (deleteData.length > 0) {
    for (i = 0; i < deleteData.length ; i++) {
      removeAgentTasksStatement = removeAgentTasksStatement + deleteData[i].oid;
      if (i != deleteData.length-1) {
        removeAgentTasksStatement = removeAgentTasksStatement + ", ";
      } else {
        removeAgentTasksStatement = removeAgentTasksStatement + "";
      }
    }
    removeAgentTasksStatement = removeAgentTasksStatement + ");";
  }

  util.log("DEBUG", "remove agent tasks sql statement: " + removeAgentTasksStatement, api_caller, "createRemoveAgentTasksStatement", logFlag);
  return removeAgentTasksStatement;
}



//mid, owner, botid, esd, ecd, asd, abd, aad, afd, acd, status, category, phrase, pseudoStore, type
function createUpdateAgentTasksStatement(tasksData, logFlag) {
  var i, j;
  util.log("DEBUG",'creating update agent tasks db ---------------------------------->' + JSON.stringify(tasksData), api_caller, "createUpdateAgentTasksStatement", logFlag);
  var updateAgentTasksStatement = "UPDATE AGENT_TASKS SET ";
  if (tasksData.length > 0) {
    for (i = 0; i < tasksData.length ; i++) {
      updateAgentTasksStatement = updateAgentTasksStatement + "owner = " + "\'" + tasksData[i].owner + "\', ";
      updateAgentTasksStatement = updateAgentTasksStatement + "botid = "  + "" + tasksData[i].botid.toString() + ", ";
      updateAgentTasksStatement = updateAgentTasksStatement + "ticket = "  + "" + tasksData[i].ticket.toString() + ", ";
      updateAgentTasksStatement = updateAgentTasksStatement + "status = "  + "\'" + tasksData[i].status + "\', ";  
      updateAgentTasksStatement = updateAgentTasksStatement + "createon = "  + "\'" + tasksData[i].createon + "\', "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "esd = "  + "\'" + tasksData[i].esd + "\', "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "ecd = "  + "\'" + tasksData[i].ecd + "\', "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "asd = "  + "\'" + tasksData[i].asd + "\', "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "abd = "  + "\'" + tasksData[i].abd + "\', ";
      updateAgentTasksStatement = updateAgentTasksStatement + "aad = "  + "\'" + tasksData[i].aad + "\', "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "afd = "  + "\'" + tasksData[i].afd + "\', "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "acd = "  + "\'" + tasksData[i].acd + "\', ";  
      
      updateAgentTasksStatement = updateAgentTasksStatement + "esttime = "  + "" + tasksData[i].esttime.toString() + ", "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "runtime = "  + "" + tasksData[i].runtime.toString() + ", "; 

      updateAgentTasksStatement = updateAgentTasksStatement + "trepeat = "  + "" + tasksData[i].trepeat.toString() + ", "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "cuspas = "  + "\'" + tasksData[i].cuspas + "\', "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "category = "  + "\'" + tasksData[i].category + "\', "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "phrase = "  + "\'" + tasksData[i].phrase + "\', "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "pseudoStore = "  + "\'" + tasksData[i].pseudoStore + "\', "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "pseudoBrand = "  + "\'" + tasksData[i].pseudoBrand + "\', "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "pseudoASIN = "  + "\'" + tasksData[i].pseudoASIN + "\', "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "type = "  + "\'" + tasksData[i].type + "\', "; 
      updateAgentTasksStatement = updateAgentTasksStatement + "asserver = "  + "" + tasksData[i].as_server + ", "; 
      
      if (typeof tasksData[i].config === 'string') {
        updateAgentTasksStatement = updateAgentTasksStatement + "config = "  + "\'" + tasksData[i].config + "\', "; 
      } else {
        updateAgentTasksStatement = updateAgentTasksStatement + "config = "  + "\'" + JSON.stringify(tasksData[i].config) + "\', "; 
      }
      updateAgentTasksStatement = updateAgentTasksStatement + "skills = "  + "\'" + tasksData[i].skills + "\' "; 

      // updateAgentTasksStatement = updateAgentTasksStatement + "delDate = "  + "\'" + tasksData[i].delDate + "\' "; 

      updateAgentTasksStatement = updateAgentTasksStatement + "WHERE mid = " + tasksData[i].mid;
      updateAgentTasksStatement = updateAgentTasksStatement + ";";
    }
  }

  util.log("DEBUG", updateAgentTasksStatement, api_caller, "createUpdateAgentTasksStatement", logFlag);
  return updateAgentTasksStatement;
}



//mid, owner, botid, esd, ecd, asd, abd, aad, afd, acd, status, category, phrase, pseudoStore, type
function createUpdateAgentTasksStatusStatement(tasksData, logFlag) {
  var i, j;
  util.log("DEBUG",'creating updaet mission status db ---------------------------->' + JSON.stringify(tasksData), api_caller, "createUpdateAgentTasksStatement", logFlag);
  var updateAgentTasksStatement = "UPDATE AGENT_TASKS SET ";
  if (tasksData.length > 0) {
    for (i = 0; i < tasksData.length ; i++) {

      updateAgentTasksStatement = updateAgentTasksStatement + "status = "  + "\'" + tasksData[i].status + "\', ";  
      
      updateAgentTasksStatement = updateAgentTasksStatement + "acd = "  + "\'" + tasksData[i].acd + "\', ";  
      
      updateAgentTasksStatement = updateAgentTasksStatement + "runtime = "  + "" + tasksData[i].runtime.toString() + " "; 

      // updateAgentTasksStatement = updateAgentTasksStatement + "delDate = "  + "\'" + tasksData[i].delDate + "\' "; 

      updateAgentTasksStatement = updateAgentTasksStatement + "WHERE mid = " + tasksData[i].mid;
      updateAgentTasksStatement = updateAgentTasksStatement + ";";
    }
  }

  util.log("DEBUG", updateAgentTasksStatement, api_caller, "createUpdateAgentTasksStatement", logFlag);
  return updateAgentTasksStatement;
}



function createQueryAfterAddAgentTasksStatement(tasksData, callback, logFlag) {
  var i, j, pid;
  util.log("DEBUG", 'creating query agent tasks statements--------------------->', api_caller, "createQueryAfterAddAgentTasksStatement", logFlag);
  
  if (tasksData.length > 0) {
    var queryAgentTasksStatement = "SELECT * FROM AGENT_TASKS WHERE ";
    for (i = 0; i < tasksData.length ; i++) {
      queryAgentTasksStatement = queryAgentTasksStatement + "( ataskid = " + tasksData[i].botid + " AND";
      queryAgentTasksStatement = queryAgentTasksStatement + " type = \'" + tasksData[i].type + "\' AND ";
      queryAgentTasksStatement = queryAgentTasksStatement + " createon = \'" + tasksData[i].createon + "\' ) ";
      if (i != tasksData.length-1) {
        queryAgentTasksStatement = queryAgentTasksStatement + " OR ";
      } else {
        queryAgentTasksStatement = queryAgentTasksStatement + ";";
      }
    }
  }
  util.log("DEBUG", queryAgentTasksStatement, api_caller, "createQueryAfterAddAgentTasksStatement", logFlag);
  return queryAgentTasksStatement;
}





// chatgpt version taking care of possible NULL value for createon
function createQueryAgentTasksStatement(qsettings, owner, callback, logFlag) {
  console.log("DEBUG: Creating query agent tasks statement...");
  
  let standardBackDate = new Date();
  standardBackDate.setDate(standardBackDate.getDate() - 2); // Go back 2 days
  let standardBackDateString = standardBackDate.toISOString().slice(0, 19).replace("T", " ");

  let queryAgentTasksStatement = "SELECT * FROM AGENT_TASKS WHERE owner = :owner AND createon > :standard_back_date";

  const params = [
    { name: "owner", value: { stringValue: owner } },
    { name: "standard_back_date", value: { stringValue: standardBackDateString } },
  ];

  if ('created_date_range' in qsettings) {
    let qwords = qsettings["created_date_range"].split(",");
    let createdEarlierDate = qwords[0];
    let createdLaterDate = qwords[1];
    
    queryAgentTasksStatement += " AND createon BETWEEN :createdEarlier AND :createdLater";
    params.push({ name: "createdEarlier", value: { stringValue: createdEarlierDate } });
    params.push({ name: "createdLater", value: { stringValue: createdLaterDate } });
  }

  if ('status' in qsettings) {
    queryAgentTasksStatement += " AND status RLIKE :status";
    params.push({ name: "status", value: { stringValue: qsettings["status"] } });
  }

  if ('type' in qsettings) {
    queryAgentTasksStatement += " AND type RLIKE :type";
    params.push({ name: "type", value: { stringValue: qsettings["type"] } });
  }

  if ('phrase' in qsettings) {
    queryAgentTasksStatement += " AND phrase RLIKE :phrase";
    params.push({ name: "phrase", value: { stringValue: qsettings["phrase"] } });
  }

  if ('pseudo_store' in qsettings) {
    queryAgentTasksStatement += " AND pseudoStore RLIKE :pseudo_store";
    params.push({ name: "pseudo_store", value: { stringValue: qsettings["pseudo_store"] } });
  }

  console.log("✅ Final Query:", queryAgentTasksStatement);
  console.log("✅ Query Params:", JSON.stringify(params, null, 2));

  return { queryAgentTasksStatement, params };
}


function createQueryAgentTasksByIdsStatement(qsettings, callback, logFlag) {
  var i, j, pid;
  util.log("DEBUG", 'creating query missions statements---------------------------------->', api_caller, "createQueryAgentTasksByIdsStatement", logFlag);
  // Extract all "mid" values into an array "mids"
  // const mids = qsettings.map(item => item.mid);
  const tids = [qsettings.ataskid];

  // Convert "mids" to a comma-separated string for the SQL query
  const tidsString = tids.join(',');


  var queryAgentTasksStatement = `SELECT * FROM AGENT_TASKS WHERE ataskid IN (${tidsString});`;
  

  util.log("DEBUG", queryAgentTasksStatement, api_caller, "createQueryAgentTasksByIdsStatement", logFlag);
  return queryAgentTasksStatement;
}


function createQueryAgentTasksByConfigStatement(api_in, callback, logFlag) {

  util.log("DEBUG", 'creating query missions config---------------------------------->', api_caller, "createQueryAgentTasksByConfigStatement", logFlag);
  // Extract all "mid" values into an array "mids"
  // const mids = qsettings.map(item => item.mid);
  const owner = api_in.owner;
  const requester = api_in.requester;
  const config_partial = api_in.config;
  

  var queryAgentTasksStatement = `SELECT * FROM AGENT_TASKS WHERE (config LIKE '%${requester}%' AND config LIKE '%${config_partial}%' AND owner = '${owner}');`;
  

  util.log("DEBUG", queryAgentTasksStatement, api_caller, "createQueryAgentTasksByConfigStatement", logFlag);
  return queryAgentTasksStatement;
}



const agent_task_template = {
  ataskid : 0,
  owner : "",
  name : "",
  description : "",
  objectives : "inactive",
  status : "inactive",
  schedule: {},
  metadata: {},
  start: "",
  priority : ""
};

//data format conversion from mysql db records type to the desired data structure type.
function convertAgentTaskRecords(taskrecords) {
  var tasks = [];
  var td;
  var i = 0;
  for (var taskrec of taskrecords.records) {
      i = 0;
      td = Object.create(agent_task_template);
      td.ataskid = mrec[i++]['longValue'];
      td.owner = taskrec[i++]['stringValue'];
      td.name = taskrec[i++]['longValue'];
      td.description = taskrec[i++]['stringValue'];
      td.objectives = JSON.parse(taskrec[i++]['stringValue']);
      td.status = taskrec[i++]['stringValue'];
      td.schedule = taskrec[i++]['stringValue'];
      td.metadata = taskrec[i++]['stringValue'];
      td.start = taskrec[i++]['booleanValue'];
      td.priority = taskrec[i++]['stringValue'];
      
      tasks.push(td);
  }

  return tasks;
}



//get all tasks owned by this user
function getAgentTasks(owner, callback, test_stub) {
  var i;
  var sqlStatement = "SELECT * FROM AGENT_TASKS WHERE owner='"+owner+"' OR owner='public';" ;
  util.log("DEBUG", "TESTSTUB: " + JSON.stringify(test_stub), api_caller, "getAgentTasks", logFlag);
  
  if ((!test_stub["testmode"]) || (test_stub["testmode"] && !test_stub['skip_getAgentTasks'])) {


    util.log("DEBUG", "get agent tasks statement: " + sqlStatement, api_caller, "getAgentTasks", logFlag);
    const params = {
      secretArn: Secrets,  
      resourceArn: Cluster, 
      sql: sqlStatement,
      database: DB  
    };
    
    util.log("DEBUG", "get all pub and my agent tasks ....", api_caller, "getAgentTasks", logFlag);
  
    return rdsExecute(params)
    // ToDo: need another step here to update person's male/female by query male/female database using the first name.
    // need another step here to update person's ethnicy by query ethnicity last name table.
    .catch (error => {
      util.log("ERROR", "get agent tasks ....oh no", api_caller, "getAgentTasks", logFlag);
      errMsg = JSON.stringify(error.message);
      err(99, error.message, callback);
    });

  } else {
    return Promise.resolve(test_stub['getAgentTasks'])
  }
}


// this function fetches all bots under the input owner
// assume: ids.length > 0
function getAgentTasksByIds(ids, callback, test_stub) {
  var i;
  var sqlStatement = "SELECT * FROM AGENT_TASKS WHERE ataskid in ( " ;
  
  if (ids.length > 0) {

    for(i=0; i < ids.length-1 ; i++) {
      sqlStatement = sqlStatement + ids[i] + ", ";
    }
    sqlStatement = sqlStatement + ids[i];
    
    
    sqlStatement = sqlStatement + " );";
    util.log("DEBUG", "get mids statement: " + sqlStatement, api_caller, "getAgentTasksByIds", logFlag);
    const params = {
      secretArn: Secrets,  
      resourceArn: Cluster, 
      sql: sqlStatement,
      database: DB  
    };
    
    util.log("DEBUG", "get all agent tasks with IDs ....", api_caller, "getAgentTasksByIds", logFlag);
  
    return rdsExecute(params)
    // ToDo: need another step here to update person's male/female by query male/female database using the first name.
    // need another step here to update person's ethnicy by query ethnicity last name table.
    .catch (error => {
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
    });
  } else {
    return Promise.resolve([]);
  }
}





function addAgentTasks(inData, callback, logFlag, test_stub) {
  let batchSize = 16; // Define the maximum batch size
  let batches = [];
  let updatedMissions = [];

  // Split inData into smaller batches
  for (let i = 0; i < inData.length; i += batchSize) {
      batches.push(inData.slice(i, i + batchSize));
  }

  util.log("DEBUG", `Total batches to process: ${batches.length}`, api_caller, "addMissions", logFlag);

  // Create a function to process each batch
  const processBatch = (batch, batchIndex) => {
      return new Promise((resolve, reject) => {
          const newMissionsString = createNewMissionsStatement(batch, callback, logFlag);

          util.log("DEBUG", `Executing batch ${batchIndex + 1}: ${newMissionsString}`, api_caller, "addMissions", logFlag);

          const params = {
              secretArn: Secrets,
              resourceArn: Cluster,
              sql: newMissionsString,
              database: DB
          };

          rdsExecute(params)
              .then(() => queryMissionsAfterAdd(batch, callback, logFlag, test_stub))
              .then((mrecs) => {
                  if (mrecs["records"].length === batch.length) {
                      updatedMissions.push(...convertMissionRecords(mrecs));
                      resolve();
                  } else {
                      reject(new Error(`# of items added not matching input in batch ${batchIndex + 1}`));
                  }
              })
              .catch((error) => {
                  util.log("ERROR", `Batch ${batchIndex + 1} failed: ${error.message}`, api_caller, "addMissions", logFlag);
                  reject(error);
              });
      });
  };

  // Chain promises to process each batch sequentially
  let chain = Promise.resolve();

  batches.forEach((batch, index) => {
      chain = chain.then(() => processBatch(batch, index));
  });

  return chain
      .then(() => {
          util.log("DEBUG", `All batches processed successfully`, api_caller, "addMissions", logFlag);
          return Promise.resolve(updatedMissions);
      })
      .catch((error) => {
          util.log("ERROR", `Error in addMissions: ${error.message}`, api_caller, "addMissions", logFlag);
          err(99, error.message, callback);
      });
}




// this function fetches all missions with botid that matches a list of input bot Ids.
function getMissionsWithMissionIds(mids, callback, test_stub) {
  var i;
  var sqlStatement = "SELECT * FROM MISSIONS WHERE mid in ( ";
  
  if ((!test_stub["testmode"]) || (test_stub["testmode"] && !test_stub['skip_getMissionsWithMissionIds'])) {
    for(i=0; i < mids.length-1 ; i++) {
      sqlStatement = sqlStatement + mids[i] + ", ";
    }
    sqlStatement = sqlStatement + mids[i];
    
    
    sqlStatement = sqlStatement + " );";
    
    const params = {
      secretArn: Secrets,  
      resourceArn: Cluster, 
      sql: sqlStatement,
      database: DB  
    };
    
    util.log("DEBUG", "get all missions with certain mids ...."+sqlStatement, api_caller, "getMissionsWithMissionIds", logFlag);
  
    return rdsExecute(params)
    // ToDo: need another step here to update person's male/female by query male/female database using the first name.
    // need another step here to update person's ethnicy by query ethnicity last name table.
    .catch (error => {
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
    });
  } else {
    return Promise.resolve(test_stub['getMissionsWithMissionIds'])
  }

}

// this function fetches all missions with botid that matches a list of input bot Ids. no need to check owners because bots are unique to owners....
function getMissionsWithBotIds(bids, callback, test_stub) {
  var i;
  var sqlStatement = "SELECT * FROM MISSIONS WHERE botid in ( "; 
  
  if ((!test_stub["testmode"]) || (test_stub["testmode"] && !test_stub['skip_getMissionsWithBotIds'])) {

    if (bids.length > 0) {
      for(i=0; i < bids.length-1 ; i++) {
        sqlStatement = sqlStatement + bids[i] + ", ";
      }
      sqlStatement = sqlStatement + bids[i];
      
      
      sqlStatement = sqlStatement + " );";
      
      const params = {
        secretArn: Secrets,  
        resourceArn: Cluster, 
        sql: sqlStatement,
        database: DB  
      };
      
      util.log("DEBUG", "get all missions under Ids ...."+sqlStatement, api_caller, "getMissionsWithBotIds", logFlag);
    
      return rdsExecute(params)
      // ToDo: need another step here to update person's male/female by query male/female database using the first name.
      // need another step here to update person's ethnicy by query ethnicity last name table.
      .catch (error => {
          errMsg = JSON.stringify(error.message);
          err(99, error.message, callback);
      });
    } else {
      return Promise.resolve([]);
    }
  } else {
    return Promise.resolve(test_stub['getMissionsWithBotIds'])
  }

}


function get1PageOfMissions(owner, pageSize, offset, days, callback, logflag, test_stub) {
  var sqlStatement = "SELECT * FROM MISSIONS WHERE owner = '" + owner + 
  "' AND esd >= DATE_SUB(CURDATE(), INTERVAL " + days.toString() + " DAY) " +
  "AND esd < (CURDATE() + INTERVAL 1 DAY) LIMIT " + pageSize.toString() + " OFFSET " + offset.toString();

  const params = {
    secretArn: Secrets,
    resourceArn: Cluster,
    sql: sqlStatement,
    database: DB
  };
  util.log("DEBUG", "get 1 page of missions ...."+sqlStatement, api_caller, "get1PageOfMissions", logFlag);
  return rdsExecute(params);
}

// this function fetches all bots under the input owner
function getAgentTaskRunHisotry(owner, days, callback, logflag, test_stub) {
  var sqlStatement;
  let offset = 0;
  const limit = 1000;
  let allResults = [];
  let hasMoreRows = true;

  // sqlStatement = "SELECT * FROM MISSIONS WHERE owner = \'" + owner + "\'";
  // sqlStatement = "SELECT COUNT(*) AS total FROM MISSIONS WHERE owner = \'" + owner + "\'";
  // 
  // we could potentially do a more fancy query to optimze # rows processed, which relates to 
  // run time, memory usage, etc.
  // (
  //   SELECT *
  //   FROM MISSIONS
  //   WHERE owner = 'so and so'
  //     AND (
  //         type LIKE '%string1%'
  //         OR type LIKE '%string2%'
  //         OR type LIKE '%string3%'
  //     )
  //     AND date >= DATE_SUB(CURDATE(), INTERVAL 2 DAY)
  // )
  // UNION ALL
  // (
  //     SELECT *
  //     FROM MISSIONS
  //     WHERE owner = 'so and so'
  //       AND (
  //           type LIKE '%otherString1%'
  //           OR type LIKE '%otherString2%'
  //           OR type LIKE '%otherString3%'
  //       )
  //       AND date >= DATE_SUB(CURDATE(), INTERVAL 21 DAY)
  // );
  // 
  sqlStatement = "SELECT COUNT(*) AS total FROM MISSIONS WHERE owner = '" + owner + 
  "' AND esd >= DATE_SUB(CURDATE(), INTERVAL " + days.toString() + " DAY) " +
  "AND esd < CURDATE() + INTERVAL 1 DAY;";

  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };
  
  if ((!test_stub["testmode"]) || (test_stub["testmode"] && !test_stub['skip_getMissions'])) {

    util.log("DEBUG", "get all missions under me ...."+sqlStatement, api_caller, "getMissions", logFlag);
  
    return rdsExecute(params)
    // ToDo: need another step here to update person's male/female by query male/female database using the first name.
    // need another step here to update person's ethnicy by query ethnicity last name table.
    .then(result => {
      var totalRows = result.records[0][0]["longValue"];
      const pageSize = 512;
      const numPages = Math.ceil(totalRows / pageSize);
      util.log("DEBUG", "total # of rows of the query result ...."+numPages.toString()+" "+JSON.stringify(result), api_caller, "getMissions", logFlag);
      
      // Generate the array of query tasks
      const offsets = Array.from({ length: numPages }, (_, i) => i * pageSize);
      const queries = offsets.map(offset => () => get1PageOfMissions(owner, pageSize, offset, days, callback, logflag, test_stub));

      
      // queries = offsets.map(offset => {
      //   // one promise per user token, user may have multiple tokens
      //   () => get1PageOfMissions(owner, pageSize, offset, callback, logflag, test_stub);
      // });
      
      var initialPromise = Promise.resolve([]);
      
      return queries.reduce((promiseChain, currentTask) => {
          return promiseChain.then(chainResults => 
              currentTask().then(currentResult => [...chainResults, ...currentResult.records])
          );
      }, initialPromise).then(results => {
        util.log("DEBUG", "total # of rows of the query result ...."+results.length.toString()+" "+JSON.stringify(result), api_caller, "getMissions", logFlag);
        return Promise.resolve({"records": results});
      }).catch(error => {
          console.error('Error executing queries:', error);
      });

      
      // return Promise.all(offsets.map(offset => {
      //   // one promise per user token, user may have multiple tokens
      //   return get1PageOfMissions(owner, pageSize, offset, callback, logflag, test_stub);
      // }))
      // .then(mrecs => {
      //   util.log("DEBUG", "promise all returned ...."+JSON.stringify(mrecs), api_caller, "getMissions", logFlag);
      // });
    })
    .catch (error => {
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
    });
  } else {
    util.log("DEBUG", "fake get all missions under me ...."+JSON.stringify(test_stub['getMissions']), api_caller, "getMissions", logFlag);
    return Promise.resolve(test_stub['getMissions'])
  }

}





async function queryAgentTasks(owner, inData, callback, logFlag, test_stub) {
  try {
    if (!inData) {
      console.log("❌ No input data provided for mission query.");
      return null;
    }

    let { queryMissionsStatement, params } = createQueryMissionsStatement(inData, owner, callback, logFlag);

    const rdsParams = {
      secretArn: Secrets,
      resourceArn: Cluster,
      sql: queryMissionsStatement,
      database: DB,
      includeResultMetadata: true,
      parameters: params
    };

    console.log("✅ Executing Query...");
    const response = await rdsClient.send(new ExecuteStatementCommand(rdsParams));
    console.log("response rec: ", (typeof response.records), JSON.stringify(response.records));
    // Convert the response into JSON
    // const records = response.records.map(row => {
    //   return row.reduce((acc, field, index) => {
    //     acc[response.columnMetadata[index].name] = Object.values(field)[0];
    //     return acc;
    //   }, {});
    // });
    const foundMissions = convertMissionRecords(response);

    // console.log("✅ Query Results:", JSON.stringify(records, null, 2));

    return JSON.stringify(foundMissions);
  } catch (error) {
    console.error("❌ Error executing MySQL statement:", error);
    throw new Error("MySQL statement error");
  }
}




function queryAgentTasksByIds(inData, callback, logFlag, test_stub) {
  var qMissionsString;

  var sqlStatement = "SELECT MAX(mid) FROM MISSIONS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };

  if (inData) {
    qMissionsString = createQueryMissionsByMidsStatement(inData, callback, logFlag);
    util.log("DEBUG", "query missions by ids...." + qMissionsString, api_caller, "queryMissionsByMids", logFlag);
    params.sql = qMissionsString;
    return rdsExecute(params)
    .then(mrecs => {
      var foundMissions = convertMissionRecords(mrecs);
      return Promise.resolve(JSON.stringify(foundMissions));
    })
    .catch (error => {
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
    });
  } else {
    return Promise.resolve(null);
  }
}


function queryMissionsByConfig(inData, callback, logFlag, test_stub) {
  var qMissionsString;

  var sqlStatement = "SELECT MAX(mid) FROM MISSIONS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };

  if (inData) {
    qMissionsString = createQueryMissionsByConfigStatement(inData, callback, logFlag);
    util.log("DEBUG", "query missions by config...." + qMissionsString, api_caller, "queryMissionsByConfig", logFlag);
    params.sql = qMissionsString;
    return rdsExecute(params)
    .then(mrecs => {
      var foundMissions = convertMissionRecords(mrecs);
      return Promise.resolve(JSON.stringify(foundMissions));
    })
    .catch (error => {
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
    });
  } else {
    return Promise.resolve(null);
  }
}




function removeAgentTasks(inData, callback, logFlag, test_stub) {
  var removeString;
  var n = inData.length;

  var lastKey = 0;
  var sqlStatement = "SELECT MAX(PID) FROM BOTS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };
  
  util.log("DEBUG", "removing agent tasks....", api_caller, "removeAgentTasks", logFlag);

  removeString = createRemoveAgentTasksStatement(inData, logFlag);
  params.sql = removeString;
  return rdsExecute(params)
  .catch (error => {
      errMsg = JSON.stringify(error.message);
      err(99, error.message, callback);
  });
}




// update bots database for the bots to be updated.
function updateBotsLevelStatus(bots2bu, callback, logFlag, test_stub) {
  var updateBotsString;
  
  var sqlStatement = "SELECT MAX(PID) FROM BOTS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };
  
  util.log("DEBUG", "updating bots, levels, levelstart, and status....", api_caller, "updateBotsLevelStatus", logFlag);

  //then merge the data from DB with the data from the client side, finally update DB
  updateBotsString = createUpdateBotsStatsStatement(bots2bu, logFlag);
  params.sql = updateBotsString;
  util.log("DEBUG", "update parames: " + JSON.stringify(params), api_caller, "updateBotsLevelStatus", logFlag);

  //finally update in DB.
  return rdsExecute(params)
  .catch (error => {
      errMsg = JSON.stringify(error.message);
      err(99, error.message, callback);
  });
}



function updateMissions(inDatas, callback, logFlag, test_stub) {
  var updateMissionsString;
  var mids = inDatas.map(function(a) {return a.mid;});
  var tickets = inDatas.map(function(a) {return a.ticket;});
  var ob_mids = tickets.filter(ticket => {ticket != 0});
  var combined_mids = mids.concat(ob_mids);
  var found_inData;
  var asy, asdate;
  var buy_step;
  var today = new Date();
  var this_year = today.getFullYear();

  // find out the last primary key of the main table, and generate pids from that number.
  var n = inDatas.length;
  var today = new Date();
  var mdata = [];

  var lastKey = 0;
  var sqlStatement = "SELECT MAX(PID) FROM BOTS";
  const params = {
    secretArn: Secrets,
    resourceArn: Cluster,
    sql: sqlStatement,
    database: DB  
  };
  
  util.log("DEBUG", "updating missions....", api_caller, "updateMissions", logFlag);
  
  return getMissionsByIds(combined_mids, callback, test_stub)
  .then(mrecs => {
    let dbrecs = mrecs.records;

    if (dbrecs.length > 0) {
      mdata = convertMissionRecords(mrecs);
    }
    
    util.log("DEBUG", "mission converted: " + JSON.stringify(mdata), api_caller, "updateMissions", logFlag);

    
    // now sync up the data with input.
    for (var inData of inDatas) {
      //find from mdata with the same mid as this inData
      const found = mdata.find(element => element.mid == inData.mid);
      const found_om = mdata.find(element => element.ticket == inData.ticket);
      util.log("DEBUG", "mission found:  " + JSON.stringify(found), api_caller, "updateMissions", logFlag);
      util.log("DEBUG", "inData:  " + JSON.stringify(inData), api_caller, "updateMissions", logFlag);

      if (found != undefined) {
        // copy over the value....
        found.botid = inData.botid;
        found.cuspas = inData.cuspas;
        found.category = inData.search_cat;
        found.phrase = inData.search_kw;
        found.status = inData.status;
        found.trepeat = inData.trepeat;
        found.pseudoStore = inData.store;
        found.pseudoBrand = inData.brand;
        found.pseudoASIN = inData.asin;
        found.as_server = inData.as_server;
        if (inData.ticket == 0) {
          // can change type only if it's not an intermediate Buy
          found.type = inData.mtype;
        }
        found.config = inData.config;
        found.skills = inData.skills;
        // found.asd = inData.asd;
        // found.acd = inData.acd;
        //======= done update directly from client side.
        
        // config is not used at this time, but could potentially be used for user manually setting esttime, asd, abd, aad, afd, acd.....
        // for now, to make things less complicated, no action here.... all those dates and time will be automatically handled. users
        // have no option to set them manually.
        
        // take care of update for intermediate buy missions, because they could affect the original buy mission.
        if (found.ticket > 0) {
          if (found.status.includes("Completed")) {
            buy_step = found.type.split("_")[1];
            switch (buy_step) {
              case "InCart":
                found_om.asd = found.asd;
                break;
    
              case "Paid":
                found_om.abd = found.acd;
                
                asdate = new Date(found_om.asd);
                asy = asdate.getFullYear();
          
                // in case buy and in cart executed in 1 mission.
                if (asy > (this_year + 1)) {
                  found_om.asd = found_om.abd;
                }
                break;
                
              case "Arrived":
                found_om.aad = found.acd;
                break;
                
              case "FBDone":
                found_om.afd = found.acd;
                break;
                
              case "FBConfirmed":
                found_om.acd = found.acd;
                found_om.status = "Completed"
                break;
              default:
            }
          }
        }
      }
    }
    

    updateMissionsString = createUpdateMissionsStatement(mdata, logFlag);
    params.sql = updateMissionsString;
    util.log("DEBUG", "update mission params: " + JSON.stringify(params), api_caller, "updateMissions", logFlag);

    return rdsExecute(params);
  })
  .catch (error => {
      err(99, error.message, callback);
  });
}


//up date mission by mission ID, but update only the start time and run time column.
function updateMissionsWithStartRunTimeOnly(inDatas, callback, logFlag, test_stub, slogStream) {
  var updateMissionsString;

  var sqlStatement = "SELECT MAX(PID) FROM BOTS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };
  

  updateMissionsString = createUpdateMissionsStartRunTimeStatement(inDatas, logFlag);
  params.sql = updateMissionsString;
  util.log("DEBUG", "update mission start run time params: " + updateMissionsString, api_caller, "updateMissionsWithStartRunTimeOnly", logFlag, slogStream);

  return rdsExecute(params)
  .catch (error => {
      err(99, error.message, callback);
  });
}


function updateMissionsRunResults(inDatas, callback, logFlag, test_stub) {
  var updateMissionsString;

  var sqlStatement = "SELECT MAX(PID) FROM BOTS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };
  

  updateMissionsString = createUpdateMissionsRunResultsStatement(inDatas, logFlag);
  params.sql = updateMissionsString;
  util.log("DEBUG", "update mission status, actual start run time params: " + updateMissionsString, api_caller, "updateMissionsRunResults", logFlag);

  return rdsExecute(params)
  .catch (error => {
      err(99, error.message, callback);
  });
}




// -----  agent tools related -------------------------------------------------



function createNewAgentToolsStatement(toolsData, logFlag) {
  var i, j;
  util.log("DEBUG", 'creating insert agent tools statements---------------------------------->', api_caller, "createNewAgentToolsStatement", logFlag);
  var insertAgentToolsStatement = "INSERT INTO AGENT_TOOLS VALUES ";

  if (toolsData.length > 0) {
    for (i = 0; i < toolsData.length ; i++) {
      insertAgentToolsStatement = insertAgentToolsStatement + "( ";
      insertAgentToolsStatement = insertAgentToolsStatement + "NULL, " + "\'" + toolsData[i].owner + "\', ";
      insertAgentToolsStatement = insertAgentToolsStatement + "\'" + toolsData[i].levels + "\', ";
      insertAgentToolsStatement = insertAgentToolsStatement + "\'" + toolsData[i].levelStart + "\', ";
      insertAgentToolsStatement = insertAgentToolsStatement + "\'" + toolsData[i].gender + "\', ";
      insertAgentToolsStatement = insertAgentToolsStatement + "\'" + toolsData[i].birthday + "\', ";
      insertAgentToolsStatement = insertAgentToolsStatement + "\'" + toolsData[i].interests + "\', ";
      insertAgentToolsStatement = insertAgentToolsStatement + "\'" + toolsData[i].location + "\', ";
      insertAgentToolsStatement = insertAgentToolsStatement + "\'" + toolsData[i].vehicle + "\', ";
      insertAgentToolsStatement = insertAgentToolsStatement + "\'" + toolsData[i].roles + "\', ";
      insertAgentToolsStatement = insertAgentToolsStatement + "\'" + toolsData[i].org + "\', ";
      insertAgentToolsStatement = insertAgentToolsStatement + "\'" + toolsData[i].status + "\', ";
      insertAgentToolsStatement = insertAgentToolsStatement + "\'" + toolsData[i].delDate + "\' ";

      insertAgentToolsStatement = insertAgentToolsStatement + ")";
      if (i != toolsData.length-1) {
        insertAgentToolsStatement = insertAgentToolsStatement + ", ";
      } else {
        insertAgentToolsStatement = insertAgentToolsStatement + ";";
      }
    }
  }
  util.log("DEBUG", insertAgentToolsStatement, api_caller, "createNewAgentToolsStatement", logFlag);
  return insertAgentToolsStatement;
}

// TODO: do we really want to delete from the DB? (or just mark them as done, maybe keep a 12 month grace period)
// should we delete the agents associated with the agid s as well?
function createRemoveAgentToolsStatement(deleteData, logFlag) {
  var i;
  util.log("DEBUG", 'deleting from the agent tools db ---------------->' + JSON.stringify(deleteData), api_caller, "createRemoveAgentToolsStatement", logFlag);
  var removeAgentToolsStatement = "DELETE FROM AGENT_TOOLS WHERE toolid IN ( ";
  if (deleteData.length > 0) {
    for (i = 0; i < deleteData.length ; i++) {
      removeAgentToolsStatement = removeAgentToolsStatement + deleteData[i].oid;
      if (i != deleteData.length-1) {
        removeAgentToolsStatement = removeAgentToolsStatement + ", ";
      } else {
        removeAgentToolsStatement = removeAgentToolsStatement + "";
      }
    }
    removeAgentToolsStatement = removeAgentToolsStatement + ");";
  }

  util.log("DEBUG", removeAgentToolsStatement, api_caller, "createRemoveAgentToolsStatement", logFlag);
  return removeAgentToolsStatement;
}


// 
function createUpdateAgentToolsStatement(toolsData, pplIds, logFlag) {
  var i, j, pid;
  util.log("DEBUG", 'creating update agent tools statements----------------->', api_caller, "createUpdateAgentToolsStatement", logFlag);
  var updateAgentToolsStatement = "";

  if (toolsData.length > 0) {
    for (i = 0; i < toolsData.length ; i++) {
      updateAgentToolsStatement = updateAgentToolsStatement + "UPDATE AGENT_TOOLS SET ";
      updateAgentToolsStatement = updateAgentToolsStatement + "owner = " + "\'" + toolsData[i].owner + "\', ";
      updateAgentToolsStatement = updateAgentToolsStatement + "levels = "  + "\'" + toolsData[i].levels + "\', ";
      updateAgentToolsStatement = updateAgentToolsStatement + "levelStart = "  + "\'" + toolsData[i].levelStart + "\', "; 
      updateAgentToolsStatement = updateAgentToolsStatement + "gender = "  + "\'" + toolsData[i].gender + "\', "; 
      updateAgentToolsStatement = updateAgentToolsStatement + "birthday = "  + "\'" + toolsData[i].birthday + "\', ";
      updateAgentToolsStatement = updateAgentToolsStatement + "interests = "  + "\'" + toolsData[i].interests + "\', "; 
      updateAgentToolsStatement = updateAgentToolsStatement + "location = "  + "\'" + toolsData[i].location + "\', "; 
      updateAgentToolsStatement = updateAgentToolsStatement + "vehicle = "  + "\'" + toolsData[i].vehicle + "\', "; 
      updateAgentToolsStatement = updateAgentToolsStatement + "`roles` = "  + "\'" + toolsData[i].roles + "\', "; 
      updateAgentToolsStatement = updateAgentToolsStatement + "org = "  + "\'" + toolsData[i].org + "\', "; 
      updateAgentToolsStatement = updateAgentToolsStatement + "`status` = "  + "\'" + toolsData[i].status + "\' "; 
      // updateAgentToolsStatement = updateAgentToolsStatement + "delDate = "  + "\'" + toolsData[i].delDate + "\' "; 
      updateAgentToolsStatement = updateAgentToolsStatement + "WHERE botid = " + toolsData[i].toolid;
      updateAgentToolsStatement = updateAgentToolsStatement + ";";
    }
  }
  util.log("DEBUG", updateAgentToolsStatement, api_caller, "createUpdateAgentToolsStatement", logFlag);
  return updateAgentToolsStatement;
}




// query bots by owner, platform, app, site, name
function createQueryAgentToolsStatement(qsettings, owner, callback, logFlag) {
  var i, j, pid;
  util.log("DEBUG", 'creating query agents statements---------------------------------->', api_caller, "createQueryAgentToolsStatement", logFlag);
  

  var queryAgentToolsStatement = "SELECT * FROM AGENT_TOOLS WHERE ";
  if (qsettings["byowneruser"]) {
    queryAgentToolsStatement = queryAgentToolsStatement + "( owner = \'" + owner + "\');";
  } else {
    let qwords = qsettings["qphrase"].trim().replace(/([ .,;]+)/g,'|');
    
    queryAgentToolsStatement = queryAgentToolsStatement + "(( owner = \'" + owner + "\') AND ";

    queryAgentToolsStatement = queryAgentToolsStatement + "( levels RLIKE \'" + qwords + "\' OR ";
    queryAgentToolsStatement = queryAgentToolsStatement + " interests RLIKE \'" + qwords + "\' OR ";
    queryAgentToolsStatement = queryAgentToolsStatement + " status RLIKE \'" + qwords + "\' OR ";
    queryAgentToolsStatement = queryAgentToolsStatement + " location RLIKE \'" + qwords + "\' OR ";
    queryAgentToolsStatement = queryAgentToolsStatement + " gender RLIKE \'" + qwords + "\' ));";

  }
  

  util.log("DEBUG", queryAgentToolsStatement, api_caller, "createQueryAgentToolsStatement", logFlag);
  return queryAgentToolsStatement;
}



const agent_tool_template = {
  toolid : 0,
  owner : "",
  name : "",
  description : "",
  link : "inactive",
  protocol: "",
  status : "inactive",
  metadata: {},
  priority : ""
};

//data format conversion from mysql db records type to the desired data structure type.
function convertAgentToolRecords(toolrecords) {
  var tools = [];
  var td;
  var i = 0;
  for (var toolrec of toolrecords.records) {
      i = 0;
      td = Object.create(agent_tool_template);
      td.toolid = toolrec[i++]['longValue'];
      td.owner = toolrec[i++]['stringValue'];
      td.name = toolrec[i++]['stringValue'];
      td.description = toolrec[i++]['stringValue'];
      td.link = toolrec[i++]['stringValue'];
      td.protocol = toolrec[i++]['stringValue'];
      td.status = toolrec[i++]['stringValue'];
      td.metadata = JSON.parse(toolrec[i++]['stringValue']);
      td.price = toolrec[i++]['stringValue'];
      
      tools.push(td);
  }

  return tools;
}



//get all tasks owned by this user
function getAgentTools(owner, callback, test_stub) {
  var i;
  var sqlStatement = "SELECT * FROM TOOLS WHERE owner='"+owner+"' OR owner='public';" ;
  util.log("DEBUG", "TESTSTUB: " + JSON.stringify(test_stub), api_caller, "getAgentTools", logFlag);
  
  if ((!test_stub["testmode"]) || (test_stub["testmode"] && !test_stub['skip_getAgentTools'])) {


    util.log("DEBUG", "get agent tools statement: " + sqlStatement, api_caller, "getAgentTools", logFlag);
    const params = {
      secretArn: Secrets,  
      resourceArn: Cluster, 
      sql: sqlStatement,
      database: DB  
    };
    
    util.log("DEBUG", "get all pub and my agent tools ....", api_caller, "getAgentTools", logFlag);
  
    return rdsExecute(params)
    // ToDo: need another step here to update person's male/female by query male/female database using the first name.
    // need another step here to update person's ethnicy by query ethnicity last name table.
    .catch (error => {
      util.log("ERROR", "get agent tools ....oh no", api_caller, "getAgentTools", logFlag);
      errMsg = JSON.stringify(error.message);
      err(99, error.message, callback);
    });

  } else {
    return Promise.resolve(test_stub['getAgentTools'])
  }
}


// this function fetches all bots under the input owner
// assume: ids.length > 0
function getAgentToolsByIds(ids, callback, test_stub) {
  var i;
  var sqlStatement = "SELECT * FROM AGENT_TOOLS WHERE toolid in ( " ;
  
  if (ids.length > 0) {

    for(i=0; i < ids.length-1 ; i++) {
      sqlStatement = sqlStatement + ids[i] + ", ";
    }
    sqlStatement = sqlStatement + ids[i];
    
    
    sqlStatement = sqlStatement + " );";
    util.log("DEBUG", "get agent tools by id statement: " + sqlStatement, api_caller, "getAgentToolsByIds", logFlag);
    const params = {
      secretArn: Secrets,  
      resourceArn: Cluster, 
      sql: sqlStatement,
      database: DB  
    };
    
    util.log("DEBUG", "get all agent tools with IDs ....", api_caller, "getAgentToolsByIds", logFlag);
  
    return rdsExecute(params)
    // ToDo: need another step here to update person's male/female by query male/female database using the first name.
    // need another step here to update person's ethnicy by query ethnicity last name table.
    .catch (error => {
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
    });
  } else {
    return Promise.resolve([]);
  }
}
// -----  org tree related --------------------------------------------------
async function getOrgAgentTree(rootId, owner, ownerSub, ownerEmail, argUsername) {
  console.log("getOrgAgentTree called with rootId:", rootId, "owner:", owner, "ownerSub:", ownerSub, "ownerEmail:", ownerEmail, "argUsername:", argUsername);
  
  // Determine the effective owner for querying orgs
  const effectiveOwner = ownerSub || owner;
  
  // If no rootId provided, find user's root org by owner
  let effectiveRootId = rootId;
  if (!effectiveRootId && effectiveOwner) {
    // Get user's root org (create if doesn't exist)
    const rootResult = await orgService.getOrCreateUserRootOrg(effectiveOwner);
    if (rootResult.success && rootResult.data) {
      effectiveRootId = rootResult.data.id;
      console.log("Using user's root org:", effectiveRootId);
    }
  }
  
  // Get organizations filtered by owner
  let orgsQuery;
  let orgsParams;
  if (effectiveOwner) {
    // First ensure owner column exists
    await orgService.ensureOwnerColumn();
    orgsQuery = `SELECT id, name, description, org_type, level, sort_order, status, parent_id, created_at, updated_at, owner FROM agent_orgs WHERE owner = :owner OR owner IS NULL ORDER BY sort_order, name`;
    orgsParams = [{ name: "owner", value: { stringValue: effectiveOwner } }];
  } else {
    orgsQuery = "SELECT id, name, description, org_type, level, sort_order, status, parent_id, created_at, updated_at FROM agent_orgs ORDER BY sort_order, name";
    orgsParams = [];
  }
  
  const params = {
    secretArn: Secrets,
    resourceArn: Cluster,
    sql: orgsQuery,
    database: DB,
    parameters: orgsParams
  };
  const orgsResult = await rdsExecute(params);
  // Helper to convert MySQL datetime to ISO 8601 format
  const toISODateTime = (val) => {
    if (!val) return null;
    // Replace space with T and add Z suffix for UTC
    return val.replace(' ', 'T') + 'Z';
  };
  const orgs = orgsResult.records.map(record => ({
    id: record[0].stringValue,
    name: record[1].stringValue,
    description: record[2].stringValue,
    org_type: record[3].stringValue,
    level: record[4].longValue,
    sort_order: record[5].longValue,
    status: record[6].stringValue,
    parent_id: record[7].stringValue,
    created_at: toISODateTime(record[8].stringValue),
    updated_at: toISODateTime(record[9].stringValue),
    owner: record[10]?.stringValue || null
  }));
  console.log("Fetched orgs:", orgs.length);

  // Filter orgs to only those belonging to this user's tree
  let filteredOrgs = orgs;
  if (effectiveOwner) {
    filteredOrgs = orgs.filter(org => org.owner === effectiveOwner);
    console.log("Filtered to user's orgs:", filteredOrgs.length);
  }

  if (effectiveRootId) {
    const orgMap = new Map(filteredOrgs.map(org => [org.id, org]));
    if (!orgMap.has(effectiveRootId)) {
      return orgService.getOrgTree(effectiveRootId);
    }
  }

  // Get all agents with their org relationships - query by all owner formats
  // Build the owner conditions for agents query (similar to getAgentsByOwners)
  const agentOwnerConditions = [];
  if (owner) agentOwnerConditions.push(`a.owner = '${owner}'`);
  if (ownerEmail) {
    agentOwnerConditions.push(`a.owner = '${ownerEmail}'`);
    // Also check sanitized email format
    const sanitizedEmail = ownerEmail.replace(/[@.]/g, '_');
    if (sanitizedEmail !== owner) {
      agentOwnerConditions.push(`a.owner = '${sanitizedEmail}'`);
    }
  }
  if (ownerSub) agentOwnerConditions.push(`a.owner = '${ownerSub}'`);
  // Also check argUsername (sanitized email from frontend)
  if (argUsername && !agentOwnerConditions.some(c => c.includes(`'${argUsername}'`))) {
    agentOwnerConditions.push(`a.owner = '${argUsername}'`);
  }
  const agentOwnerWhere = agentOwnerConditions.length > 0 ? agentOwnerConditions.join(' OR ') : '1=0';
  
  console.log("getOrgAgentTree agent owner conditions:", agentOwnerConditions);
  const agentsQuery = `SELECT a.id, a.name, a.description, a.status, a.created_at, a.updated_at, a.owner, a.avatar_resource_id, r.org_id, a.extra_data FROM agents a LEFT JOIN agent_org_rels r ON a.id = r.agent_id WHERE ${agentOwnerWhere}`;
  console.log("getOrgAgentTree agents query:", agentsQuery);
  params.sql = agentsQuery;
  params.parameters = [];
  const agentsResult = await rdsExecute(params);
  const agents = agentsResult.records.map(record => {
    // Helper to convert MySQL datetime to ISO 8601 format
    const toISODateTime = (val) => {
      if (!val) return null;
      // Replace space with T and add Z suffix for UTC
      return val.replace(' ', 'T') + 'Z';
    };
    return {
      id: record[0].stringValue,
      name: record[1].stringValue,
      description: record[2].stringValue,
      status: record[3].stringValue,
      created_at: toISODateTime(record[4].stringValue),
      updated_at: toISODateTime(record[5].stringValue),
      owner: record[6].stringValue,
      avatar_resource_id: record[7].stringValue,
      org_id: record[8].stringValue,
      extra_data: record[9].stringValue
    };
  });
  console.log("Fetched agents:", agents.length);

  // Add isBound field for frontend compatibility
  agents.forEach(agent => {
    agent.isBound = agent.org_id !== null;
  });

  // Build the integrated tree
  const treeRoot = buildOrgAgentTree(filteredOrgs, agents, effectiveRootId);
  console.log("Returning treeRoot with id:", treeRoot.id);

  // Replace Cognito sub ID in root org name with user-friendly display name
  // Priority: email > derive email from sanitized username (argUsername) > owner
  let displayName = null;
  
  // If ownerEmail is a real email (contains @), use it
  if (ownerEmail && ownerEmail.includes('@')) {
    displayName = ownerEmail;
  } 
  // Try to derive email from argUsername (sanitized email from frontend, e.g., songc_yahoo_com)
  else if (argUsername && argUsername.includes('_')) {
    const parts = argUsername.split('_');
    if (parts.length >= 3) {
      // Attempt to reconstruct: name_domain_tld -> name@domain.tld
      const tld = parts.pop(); // e.g., 'com'
      const domain = parts.pop(); // e.g., 'yahoo'
      const name = parts.join('_'); // in case username has underscores
      displayName = `${name}@${domain}.${tld}`;
      console.log("Derived email from argUsername:", argUsername, "->", displayName);
    }
  }
  // Fallback: try to derive from owner if it looks like sanitized email
  else if (owner && owner.includes('_')) {
    const parts = owner.split('_');
    if (parts.length >= 3) {
      const tld = parts.pop();
      const domain = parts.pop();
      const name = parts.join('_');
      displayName = `${name}@${domain}.${tld}`;
    }
  }
  
  // Replace the org name if it matches the Cognito sub ID
  // Check root and recursively check all nodes in the tree
  const replaceSubIdWithDisplayName = (node) => {
    if (!node) return;
    if (node.name === effectiveOwner && displayName) {
      node.name = displayName;
      console.log("Replaced org name with display name:", displayName, "in node:", node.id);
    }
    if (node.children && Array.isArray(node.children)) {
      node.children.forEach(child => replaceSubIdWithDisplayName(child));
    }
  };
  
  if (treeRoot && displayName) {
    replaceSubIdWithDisplayName(treeRoot);
  }

  return treeRoot;
}

function buildOrgAgentTree(orgs, agents, rootId) {
  // Create agent lookup by org_id
  const agentsByOrg = new Map();
  const unassignedAgents = [];

  agents.forEach(agent => {
    const orgId = agent.org_id;
    if (orgId) {
      if (!agentsByOrg.has(orgId)) {
        agentsByOrg.set(orgId, []);
      }
      agentsByOrg.get(orgId).push(agent);
    } else {
      unassignedAgents.push(agent);
    }
  });

  // Build org lookup
  const orgMap = new Map();
  orgs.forEach(org => {
    orgMap.set(org.id, org);
  });

  // Build parent-child relationships
  const childrenMap = new Map();
  const rootCandidates = [];

  if (rootId && orgMap.has(rootId)) {
    rootCandidates.push(orgMap.get(rootId));
  } else {
    orgs.forEach(org => {
      const parentId = org.parent_id;
      if (parentId && orgMap.has(parentId)) {
        if (!childrenMap.has(parentId)) {
          childrenMap.set(parentId, []);
        }
        childrenMap.get(parentId).push(org);
      } else {
        rootCandidates.push(org);
      }
    });
  }

  // Create virtual root if needed
  if (rootCandidates.length === 0) {
    rootCandidates.push({
      id: '__virtual_root__',
      name: 'eCan.ai',
      description: 'Root Organization',
      org_type: 'company',
      level: 0,
      sort_order: 0,
      status: 'active',
      parent_id: null,
      created_at: null,
      updated_at: null,
    });
  }

  function buildTreeNode(orgData) {
    const node = {
      id: orgData.id,
      name: orgData.name,
      description: orgData.description || '',
      org_type: orgData.org_type || 'department',
      level: orgData.level || 0,
      sort_order: orgData.sort_order || 0,
      status: orgData.status || 'active',
      parent_id: orgData.parent_id,
      created_at: orgData.created_at,
      updated_at: orgData.updated_at,
      agents: agentsByOrg.get(orgData.id) || [],
      children: []
    };

    // Recursively build children
    const childOrgs = childrenMap.get(orgData.id) || [];
    childOrgs.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0) || a.name.localeCompare(b.name));

    childOrgs.forEach(childOrg => {
      node.children.push(buildTreeNode(childOrg));
    });

    return node;
  }

  // Build tree starting from root
  let treeRoot;
  if (rootCandidates.length === 1) {
    treeRoot = buildTreeNode(rootCandidates[0]);
  } else {
    treeRoot = {
      id: '__virtual_root__',
      name: 'Organizations',
      description: 'Virtual root node',
      org_type: 'company',
      level: 0,
      sort_order: 0,
      status: 'active',
      parent_id: null,
      created_at: null,
      updated_at: null,
      children: rootCandidates
        .sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0) || a.name.localeCompare(b.name))
        .map(org => buildTreeNode(org)),
      agents: []
    };
  }

  // Add unassigned agents to root
  treeRoot.agents.push(...unassignedAgents);

  return treeRoot;
}

// -----  knowleges related -------------------------------------------------


function createNewKnowledgesStatement(knowledgesData, logFlag) {
  var i, j;
  util.log("DEBUG", 'creating insert knowledges statements---------------------------------->', api_caller, "createNewKnowledgesStatement", logFlag);
  var insertKnowledgesStatement = "INSERT INTO KNOWLEDGES VALUES ";

  if (knowledgesData.length > 0) {
    for (i = 0; i < knowledgesData.length ; i++) {
      insertKnowledgesStatement = insertKnowledgesStatement + "( ";
      insertKnowledgesStatement = insertKnowledgesStatement + "NULL, " + "\'" + knowledgesData[i].owner + "\', ";
      insertKnowledgesStatement = insertKnowledgesStatement + "\'" + knowledgesData[i].levels + "\', ";
      insertKnowledgesStatement = insertKnowledgesStatement + "\'" + knowledgesData[i].levelStart + "\', ";
      insertKnowledgesStatement = insertKnowledgesStatement + "\'" + knowledgesData[i].gender + "\', ";
      insertKnowledgesStatement = insertKnowledgesStatement + "\'" + knowledgesData[i].birthday + "\', ";
      insertKnowledgesStatement = insertKnowledgesStatement + "\'" + knowledgesData[i].interests + "\', ";
      insertKnowledgesStatement = insertKnowledgesStatement + "\'" + knowledgesData[i].location + "\', ";
      insertKnowledgesStatement = insertKnowledgesStatement + "\'" + knowledgesData[i].vehicle + "\', ";
      insertKnowledgesStatement = insertKnowledgesStatement + "\'" + knowledgesData[i].roles + "\', ";
      insertKnowledgesStatement = insertKnowledgesStatement + "\'" + knowledgesData[i].org + "\', ";
      insertKnowledgesStatement = insertKnowledgesStatement + "\'" + knowledgesData[i].status + "\', ";
      insertKnowledgesStatement = insertKnowledgesStatement + "\'" + knowledgesData[i].delDate + "\' ";

      insertKnowledgesStatement = insertKnowledgesStatement + ")";
      if (i != knowledgesData.length-1) {
        insertKnowledgesStatement = insertKnowledgesStatement + ", ";
      } else {
        insertKnowledgesStatement = insertKnowledgesStatement + ";";
      }
    }
  }
  util.log("DEBUG", insertKnowledgesStatement, api_caller, "createNewKnowledgesStatement", logFlag);
  return insertKnowledgesStatement;
}

// TODO: do we really want to delete from the DB? (or just mark them as done, maybe keep a 12 month grace period)
// should we delete the agents associated with the agid s as well?
function createRemoveKnowledgesStatement(knowledgesData, logFlag) {
  var i;
  util.log("DEBUG", 'deleting from the agent tools db ---------------->' + JSON.stringify(deleteData), api_caller, "createRemoveKnowledgesStatement", logFlag);
  var removeKnowledgesStatement = "DELETE FROM KNOWLEDGES WHERE knid IN ( ";
  if (deleteData.length > 0) {
    for (i = 0; i < deleteData.length ; i++) {
      removeKnowledgesStatement = removeKnowledgesStatement + deleteData[i].oid;
      if (i != deleteData.length-1) {
        removeKnowledgesStatement = removeKnowledgesStatement + ", ";
      } else {
        removeKnowledgesStatement = removeKnowledgesStatement + "";
      }
    }
    removeKnowledgesStatement = removeKnowledgesStatement + ");";
  }

  util.log("DEBUG", removeKnowledgesStatement, api_caller, "createRemoveKnowledgesStatement", logFlag);
  return removeKnowledgesStatement;
}


// 
function createUpdateKnowledgesStatement(knowledgesData, pplIds, logFlag) {
  var i, j, pid;
  util.log("DEBUG", 'creating update agent tools statements----------------->', api_caller, "createUpdateKnowledgesStatement", logFlag);
  var updateKnowledgesStatement = "";

  if (knowledgesData.length > 0) {
    for (i = 0; i < toolsData.length ; i++) {
      updateKnowledgesStatement = updateKnowledgesStatement + "UPDATE KNOWLEDGES SET ";
      updateKnowledgesStatement = updateKnowledgesStatement + "owner = " + "\'" + knowledgesData[i].owner + "\', ";
      updateKnowledgesStatement = updateKnowledgesStatement + "levels = "  + "\'" + knowledgesData[i].levels + "\', ";
      updateKnowledgesStatement = updateKnowledgesStatement + "levelStart = "  + "\'" + knowledgesData[i].levelStart + "\', "; 
      updateKnowledgesStatement = updateKnowledgesStatement + "gender = "  + "\'" + knowledgesData[i].gender + "\', "; 
      updateKnowledgesStatement = updateKnowledgesStatement + "birthday = "  + "\'" + knowledgesData[i].birthday + "\', ";
      updateKnowledgesStatement = updateKnowledgesStatement + "interests = "  + "\'" + knowledgesData[i].interests + "\', "; 
      updateKnowledgesStatement = updateKnowledgesStatement + "location = "  + "\'" + knowledgesData[i].location + "\', "; 
      updateKnowledgesStatement = updateKnowledgesStatement + "vehicle = "  + "\'" + knowledgesData[i].vehicle + "\', "; 
      updateKnowledgesStatement = updateKnowledgesStatement + "`roles` = "  + "\'" + knowledgesData[i].roles + "\', "; 
      updateKnowledgesStatement = updateKnowledgesStatement + "org = "  + "\'" + knowledgesData[i].org + "\', "; 
      updateKnowledgesStatement = updateKnowledgesStatement + "`status` = "  + "\'" + knowledgesData[i].status + "\' "; 
      // updateKnowledgesStatement = updateKnowledgesStatement + "delDate = "  + "\'" + knowledgesData[i].delDate + "\' "; 
      updateKnowledgesStatement = updateKnowledgesStatement + "WHERE botid = " + knowledgesData[i].knid;
      updateKnowledgesStatement = updateKnowledgesStatement + ";";
    }
  }
  util.log("DEBUG", updateKnowledgesStatement, api_caller, "createUpdateKnowledgesStatement", logFlag);
  return updateKnowledgesStatement;
}




// query bots by owner, platform, app, site, name
function createQueryKnowledgesStatement(qsettings, owner, callback, logFlag) {
  var i, j, pid;
  util.log("DEBUG", 'creating query agents statements---------------------------------->', api_caller, "createQueryKnowledgesStatement", logFlag);
  

  var queryKnowledgesStatement = "SELECT * FROM KNOWLEDGES WHERE ";
  if (qsettings["byowneruser"]) {
    queryKnowledgesStatement = queryKnowledgesStatement + "( owner = \'" + owner + "\');";
  } else {
    let qwords = qsettings["qphrase"].trim().replace(/([ .,;]+)/g,'|');
    
    queryKnowledgesStatement = queryKnowledgesStatement + "(( owner = \'" + owner + "\') AND ";

    queryKnowledgesStatement = queryKnowledgesStatement + "( levels RLIKE \'" + qwords + "\' OR ";
    queryKnowledgesStatement = queryKnowledgesStatement + " interests RLIKE \'" + qwords + "\' OR ";
    queryKnowledgesStatement = queryKnowledgesStatement + " status RLIKE \'" + qwords + "\' OR ";
    queryKnowledgesStatement = queryKnowledgesStatement + " location RLIKE \'" + qwords + "\' OR ";
    queryKnowledgesStatement = queryKnowledgesStatement + " gender RLIKE \'" + qwords + "\' ));";

  }
  

  util.log("DEBUG", queryKnowledgesStatement, api_caller, "createQueryKnowledgesStatement", logFlag);
  return queryKnowledgesStatement;
}



function createQueryAfterAddKnowledgesStatement(agentData, callback, logFlag) {
  var i, j, pid;
  util.log("DEBUG", 'creating query knowledges statements after add ------------------>', api_caller, "createQueryAfterAddKnowledgesStatement", logFlag);
  
  if (agentData.length > 0) {
    var queryKnowledgesStatement = "SELECT * FROM KNOWLEDGES WHERE ";
    for (i = 0; i < agentData.length ; i++) {
      queryKnowledgesStatement = queryKnowledgesStatement + "( owner = \'" + agentData[i].owner + "\' AND";
      queryKnowledgesStatement = queryKnowledgesStatement + " levelStart = \'" + agentData[i].levelStart + "\' AND ";
      queryKnowledgesStatement = queryKnowledgesStatement + " gender = \'" + agentData[i].gender + "\' AND ";
      queryKnowledgesStatement = queryKnowledgesStatement + " location = \'" + agentData[i].location + "\' AND ";
      queryKnowledgesStatement = queryKnowledgesStatement + " birthday = \'" + agentData[i].birthday + "\' AND ";
      queryKnowledgesStatement = queryKnowledgesStatement + " interests = \'" + agentData[i].interests + "\' ) ";
      if (i != agentData.length-1) {
        queryKnowledgesStatement = queryKnowledgesStatement + " OR ";
      } else {
        queryKnowledgesStatement = queryKnowledgesStatement + ";";
      }
    }
  }
  util.log("DEBUG", queryKnowledgesStatement, api_caller, "createQueryAfterAddKnowledgesStatement", logFlag);
  return queryKnowledgesStatement;
}




function getMySQLDateTime() {
  const now = new Date();

  const year = now.getFullYear();
  const month = String(now.getMonth() + 1).padStart(2, '0'); // Months are zero-based
  const day = String(now.getDate()).padStart(2, '0');
  const hours = String(now.getHours()).padStart(2, '0');
  const minutes = String(now.getMinutes()).padStart(2, '0');
  const seconds = String(now.getSeconds()).padStart(2, '0');

  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}


const knowledge_template = {
  knid : 0,
  owner : "",
  name : "",
  description : "",
  path: "",
  status : "inactive",
  metadata: {},
  rag : ""
};


function convertKnowledgeRecords(k_records) {
  var knowledges = [];
  var knowledge;
  var i = 0;
  for (var knowledge_rec of k_records.records) {
    i = 0;
    knowledge = Object.create(knowledge_template);
    knowledge.knid = knowledge_rec[i++]['longValue'];
    knowledge.owner = knowledge_rec[i++]['stringValue'];
    knowledge.name = knowledge_rec[i++]['stringValue'];
    knowledge.description = knowledge_rec[i++]['stringValue'];
    knowledge.path = knowledge_rec[i++]['stringValue'];
    knowledge.status = knowledge_rec[i++]['stringValue'];
    knowledge.metadata = JSON.parse(knowledge_rec[i++]['stringValue']);
    knowledge.rag = knowledge_rec[i++]['stringValue'];

    knowledges.push(knowledge);
  }
  
  return knowledges;
}





// the main purpose is find the just-added missions and get their mission IDs.
function queryKnowledgesAfterAdd(inData, callback, logFlag, test_stub) {
  var qAgentsString;
  var n = inData.length;

  var lastKey = 0;
  var sqlStatement = "SELECT MAX(mid) FROM AGENTS";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };

	if ((!test_stub["testmode"]) || (test_stub["testmode"] && !test_stub['skip_queryAgentsAfterAdd'])) {
        if (inData.length > 0) {
          qAgentsString = createQueryAfterAddAgentsStatement(inData, callback, logFlag);
          util.log("DEBUG", "query agents after add...." + qAgentsString);
          params.sql = qAgentsString;
          return rdsExecute(params)
          .catch (error => {
              errMsg = JSON.stringify(error.message);
              err(99, error.message, callback);
          });
        } else {
            return Promise.resolve(null);
        }
    } else {
      if (test_stub['passThruGenID_queryAgentsAfterAdd']) {

        let qmRecs = fakeQueryAgents(inData);

        util.log("DEBUG", "query bots....fake pass thru:" + JSON.stringify(qmRecs), api_caller, "queryAgentsAfterAdd", logFlag);

        return Promise.resolve(qmRecs);
      } else {
        return Promise.resolve(test_stub["queryAgentsAfterAdd"]);
      }
    }
}


function addKnowledges(inData, callback, logFlag, test_stub) {
  var newKnowledgesString;
  var n = inData.length;

  var lastKey = 0;
  var sqlStatement = "SELECT MAX(botid) FROM KNOWLEDGES";
  var newStartRow = 0;
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };
  
  util.log("DEBUG", "add new knowledges....", api_caller, "addKnowledges", logFlag);

  newKnowledgesString = createNewKnowledgesStatement(inData, logFlag);
  params.sql = newKnowledgesString;
  return rdsExecute(params)
  .then(res => {
    return queryKnowledgesAfterAdd(inData, callback, logFlag, test_stub);
	})
	.then(krecs => {
    if (krecs["records"].length == inData.length) {
        var addedknowledges = convertKnowledgeRecords(krecs);
        return Promise.resolve(addedknowledges);
    } else {
      util.log("ERROR: ", "add agents not fully successfull ....", api_caller, "addKnowledges", logFlag);
      err(97, "# of knowledges added not matching input", callback);
    }
    
  })
  .catch (error => {
    util.log("ERROR: ", "add knowledges failed....", api_caller, "addKnowledges", logFlag);
    errMsg = JSON.stringify(error.message);
    err(99, error.message, callback);
  });
}



function removeKnowledges(inData, callback, logFlag, test_stub) {
  var removeKnowledgesString;
  var n = inData.length;

  var lastKey = 0;
  var sqlStatement = "SELECT MAX(PID) FROM KNOWLEDGES";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };
  
  util.log("DEBUG", "remove knowledges....", api_caller, "removeKnowledges", logFlag);

  removeKnowledgesString = createRemoveKnowledgesStatement(inData, logFlag);
  params.sql = removeKnowledgesString;
  return rdsExecute(params)
  .catch (error => {
      errMsg = JSON.stringify(error.message);
      err(99, error.message, callback);
  });
}



function updateKnowledges(inData, bots2bu, callback, logFlag, test_stub) {
  const chunkSize = 16; // Define the chunk size for batch processing
  const Secrets = "arn:aws:secretsmanager:us-east-1:667118410653:secret:rds-db-credentials/cluster-3PWC5NJ26SWUSO74X5PDRLYS5Q/admin-6Oqidf";
  const Cluster = "arn:aws:rds:us-east-1:667118410653:cluster:ppl";
  const DB = "TPSMirror";

  // Process a single chunk of data
  function processChunk(chunk) {
    let numberOfRecordsUpdated = 0;

    return getKnowledgesByIds(chunk.map(a => a.knid), callback, logFlag, test_stub)
      .then(data => {
        util.log("DEBUG", JSON.stringify(data), api_caller, "updateKnowledges", logFlag);
        let dbrecs = data.records;

        if (dbrecs.length > 0) {
          for (let r of dbrecs) {
            let found = chunk.find(element => element.knid == r[0]["longValue"]);
            if (found) {
              found.levelStart = r[3]["stringValue"];
              found.delDate = r[10]["stringValue"];
            }
          }
        }

        // Generate individual update statements for each bot
        const updateStatements = chunk.map(knowledge => createUpdateKnowledgesStatement([knowledge], logFlag));

        // Sequentially execute each statement
        return updateStatements.reduce((promiseChain, statement) => {
          const params = {
            secretArn: Secrets,
            resourceArn: Cluster,
            sql: statement,
            database: DB,
          };

          util.log("DEBUG", "Executing update: " + statement, api_caller, "updateKnowledges", logFlag);

          return promiseChain
            .then(() => rdsExecute(params))
            .then(() => {
              numberOfRecordsUpdated++; // Increment the counter on successful execution
            });
        }, Promise.resolve());
      })
      .then(() => {
        // Return the emulated result for this chunk
        const result = { numberOfRecordsUpdated };
        util.log("DEBUG", "Chunk result: " + JSON.stringify(result), api_caller, "updateKnowledges", logFlag);
        return result;
      })
      .catch(error => {
        util.log("ERROR", "Error processing chunk: " + error.message, api_caller, "updateKnowledges", logFlag);
        throw error; // Let the caller handle the error
      });
  }

  // Main logic
  util.log("DEBUG", "Updating knowledges...", api_caller, "updateKnowledges", logFlag);

  return processAllChunks(inData)
    .then(result => {
      util.log("DEBUG", "Final result: " + JSON.stringify(result), api_caller, "updateKnowledges", logFlag);
      callback(null, result);
    })
    .catch(error => {
      util.log("ERROR", "Error in updateKnowledges: " + error.message, api_caller, "updateKnowledges", logFlag);
      callback(error, null);
    });
}

// this function fetches all bots under the input owner
// assume: ids.length > 0
function getKnowledgesByIds(ids, callback, logFlag, test_stub) {
  var i;
  var sqlStatement = "SELECT * FROM KNOWLEDGES WHERE knid in ( " ;
  util.log("DEBUG", "TESTSTUB: " +JSON.stringify(ids) + ":::"+JSON.stringify(test_stub), api_caller, "getKnowledgesByIds", logFlag);
  
  if ((!test_stub["testmode"]) || (test_stub["testmode"] && !test_stub['skip_getKnowledgesByIds'])) {
    
    if (ids.length > 0) {
  
      for(i=0; i < ids.length-1 ; i++) {
        sqlStatement = sqlStatement + ids[i] + ", ";
      }
      sqlStatement = sqlStatement + ids[i];
      
      
      sqlStatement = sqlStatement + " );";
      util.log("DEBUG", "get knowledge ids statement: " + sqlStatement, api_caller, "getKnowledgesByIds", logFlag);
      const params = {
        secretArn: Secrets,  
        resourceArn: Cluster, 
        sql: sqlStatement,
        database: DB  
      };
      
      util.log("DEBUG", "get all knowledge with IDs ...."+sqlStatement , api_caller, "getKnowledgesByIds", logFlag);
    
      return rdsExecute(params)
      // ToDo: need another step here to update person's male/female by query male/female database using the first name.
      // need another step here to update person's ethnicy by query ethnicity last name table.
      .catch (error => {
        util.log("ERROR", "getKnowledgesByIds ....oh no", api_caller, "getKnowledgesByIds", logFlag);
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
      });
    } else {
      return Promise.resolve({records:[]});
    }
  } else {
    return Promise.resolve(test_stub['getKnowledgesByIds'])
  }
}


// this function fetches all bots under the input owner
function getKnowledges(owner, callback, logflag, test_stub) {
  
  var sqlStatement = "SELECT * FROM KNOWLEDGES WHERE (owner = \'" + owner + "\' OR owner = \'public\') and status = \'active\'" ;
  util.log("DEBUG", "getKnowledges sqlStatement: " + sqlStatement, api_caller, "getKnowledges", logFlag);
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };
  
  if ((!test_stub["testmode"]) || (test_stub["testmode"] && !test_stub['skip_getKnowledges'])){
  
    util.log("DEBUG", "get all knowledge under me ....", api_caller, "getKnowledges", logFlag);
  
    return rdsExecute(params)
    // ToDo: need another step here to update person's male/female by query male/female database using the first name.
    // need another step here to update person's ethnicy by query ethnicity last name table.
    .catch (error => {
        util.log("ERROR", "getKnowledges.....oh no....", api_caller, "getKnowledges", logFlag)
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
    });
  } else {
    util.log("DEBUG", "fake get all knowledge under me ...."+JSON.stringify(test_stub['getKnowledges']), api_caller, "getKnowledges", logFlag);
    return Promise.resolve(test_stub['getKnowledges'])
  }

}



function queryKnowledges(owner, inData, callback, logFlag, test_stub) {
  var qKnowledgesString;

  var sqlStatement = "SELECT MAX(mid) FROM KNOWLEDGES";
  const params = {
    secretArn: Secrets,  
    resourceArn: Cluster, 
    sql: sqlStatement,
    database: DB  
  };

  if (inData) {
    qKnowledgesString = createQueryKnowledgesStatement(inData, owner, logFlag);
    util.log("DEBUG", "query knowledge...." + qKnowledgesString, api_caller, "queryKnowledges", logFlag);
    params.sql = qKnowledgesString;
    return rdsExecute(params)
    .then(krecs => {
      console.log("query knowedges....");
      var foundKnowledges = convertKnowledgeRecords(krecs);

      return Promise.resolve(foundKnowledges);
    })
    .catch (error => {
        errMsg = JSON.stringify(error.message);
        err(99, error.message, callback);
    });
  } else {
    return Promise.resolve(null);
  }
}



// ------------------------------------------------------------------------------------------------------------------------

function getTodayDateString() {
  const today = new Date();
  const yyyy = today.getFullYear();
  const mm = String(today.getMonth() + 1).padStart(2, "0"); // Month (1-12) → Ensure 2 digits
  const dd = String(today.getDate()).padStart(2, "0"); // Day (1-31) → Ensure 2 digits
  return `${yyyy}${mm}${dd}`;
}

function normalizeInputArray(input) {
  if (!input) return [];
  return Array.isArray(input) ? input : [input];
}

function placeholderId(prefix, fallbackId, idx) {
  if (fallbackId) return fallbackId;
  return `${prefix}_${Date.now()}_${idx}`;
}

function buildWarehousePlaceholder(input = {}, idx = 0) {
  return {
    id: placeholderId("wh", input.id, idx),
    name: input.name || "placeholder-warehouse",
    code: input.code || null,
    address: input.address || null,
    contact_name: input.contact_name || null,
    contact_phone: input.contact_phone || null,
    status: input.status || "active",
    notes: input.notes || null,
    created_at: input.created_at || new Date().toISOString(),
    updated_at: input.updated_at || new Date().toISOString()
  };
}

function buildLabelFormatPlaceholder(input = {}, idx = 0) {
  return {
    id: placeholderId("label", input.id, idx),
    name: input.name || "placeholder-label",
    carrier: input.carrier || null,
    service: input.service || null,
    size: input.size || null,
    dpi: input.dpi ?? null,
    template_url: input.template_url || null,
    settings: input.settings || null,
    status: input.status || "active",
    created_at: input.created_at || new Date().toISOString(),
    updated_at: input.updated_at || new Date().toISOString()
  };
}

function buildProductPlaceholder(input = {}, idx = 0) {
  return {
    id: placeholderId("prod", input.id, idx),
    sku: input.sku || `placeholder-sku-${idx}`,
    name: input.name || "placeholder-product",
    description: input.description || null,
    barcode: input.barcode || null,
    weight_grams: input.weight_grams ?? null,
    dimensions_cm: input.dimensions_cm || null,
    attributes: input.attributes || null,
    status: input.status || "active",
    created_at: input.created_at || new Date().toISOString(),
    updated_at: input.updated_at || new Date().toISOString()
  };
}

function buildInventoryPlaceholder(input = {}, idx = 0) {
  return {
    id: placeholderId("inv", input.id, idx),
    warehouse_id: input.warehouse_id || "placeholder-warehouse-id",
    product_id: input.product_id || "placeholder-product-id",
    on_hand: input.on_hand ?? 0,
    reserved: input.reserved ?? 0,
    available: input.available ?? (input.on_hand ?? 0) - (input.reserved ?? 0),
    bin_location: input.bin_location || null,
    status: input.status || "active",
    updated_at: input.updated_at || new Date().toISOString()
  };
}

async function processEvent(event, context, callback, test_stub) {
  var returnData;
  util.log("DEBUG", "input: " + JSON.stringify(event), api_caller, "processEvent", logFlag);
  console.log("[agentScheduler] processEvent: incoming event:", JSON.stringify(event));
  util.log("DEBUG", "lambdaVersion: " + (process.env.AWS_LAMBDA_FUNCTION_VERSION || "unknown"), api_caller, "processEvent", logFlag);
  statCode = 200;
  
  var owner;
  var requester;
  var missionTBA;
  var newStartRow;
  // Log how owner is resolved
  const UNRECOGNIZED_INPUT = {error: "Unrecognized API"};
  
  // Prefer explicit owner/userId in arguments if present
  if (event.arguments && (event.arguments.owner || event.arguments.userId || event.arguments.username)) {
    owner = event.arguments.owner || event.arguments.userId || event.arguments.username;
    requester = event.arguments.owner || event.arguments.userId || event.arguments.username;
    console.log(`[agentScheduler] processEvent: owner resolved from arguments: owner='${event.arguments.owner}', userId='${event.arguments.userId}', username='${event.arguments.username}'`);
  } else if (event.arguments?.input) {
    const inputItems = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
    const inputOwner = inputItems.find((item) => item?.owner)?.owner;
    if (inputOwner) {
      owner = inputOwner;
      requester = inputOwner;
      console.log(`[agentScheduler] processEvent: owner resolved from arguments.input: owner='${inputOwner}'`);
    }
  }

  if (!owner && event.identity?.hasOwnProperty("claims")) {
    requester = event.identity?.claims?.email || event.identity?.claims?.username || event.identity?.username || event.identity?.sub || "";
    owner = requester;
    console.log(`[agentScheduler] processEvent: owner resolved from identity claims: '${owner}'`);
  } else if (!owner) {
    requester = event.request?.headers?.["x-api-caller"] || "";
    owner = requester;
    console.log(`[agentScheduler] processEvent: owner resolved from x-api-caller header: '${owner}'`);
  }
  const ownerSub = event.identity?.sub || event.identity?.claims?.sub || event.identity?.username || "";
  // ownerEmail is the actual email from identity claims - used for querying skills/tasks/etc
  // that are stored with the email as owner (not the sanitized username from frontend)
  const ownerEmail = event.identity?.claims?.email || owner;

  const userName = (owner || "unknown").replace(/[@.]/g, "_");
  // Get today's date in YYYYMMDD format
  const today = getTodayDateString();
  // Construct S3 path: log_root/user_name/YYYYMMDD/
  const logDirectory = `${LOG_ROOT}/${userName}/${today}/`;
  // Define S3 object key (log file name)
  const scheduleLogFile = `${logDirectory}schedule.log`;


  let user_account_info = await cfiles.qualAPI(requester);

  let user_account;
  try {
    // Some upstream lambdas return the payload wrapped like { result: "<jsonstring>" } or double-encoded.
    let rawAccount = user_account_info?.result?.result ?? user_account_info?.result ?? user_account_info ?? {};
    // Peel away nested JSON strings until we reach an object.
    while (typeof rawAccount === "string") {
      try {
        rawAccount = JSON.parse(rawAccount);
      } catch (e) {
        util.log("ERROR", "Failed to parse user account raw payload: " + e.message, api_caller, "processEvent", logFlag);
        break;
      }
    }
    user_account = rawAccount;
    if (!user_account || typeof user_account !== "object") {
      user_account = { body: [] };
    }
  } catch (parseError) {
    util.log("ERROR", "Failed to parse user account payload: " + parseError.message, api_caller, "processEvent", logFlag);
    user_account = { body: [] };
  }

  util.log("DEBUG", "user_account: " + requester + " " + JSON.stringify(user_account), api_caller, "processEvent", logFlag);
  const accountBodyRaw = user_account?.body;
  let accountBody = [];
  if (Array.isArray(accountBodyRaw)) {
    accountBody = accountBodyRaw;
  } else if (typeof accountBodyRaw === "string") {
    try {
      const parsedBody = JSON.parse(accountBodyRaw);
      if (Array.isArray(parsedBody)) {
        accountBody = parsedBody;
      }
    } catch (e) {
      util.log("ERROR", "Failed to parse account body: " + e.message, api_caller, "processEvent", logFlag);
    }
  }

  const accountRecord = (Array.isArray(accountBody) && accountBody.length > 0) ? accountBody[0] : {};
  const fund = Number(accountRecord['fund'] || 0);
  const status = accountRecord['states'] || "inactive";
  const quota = Number(accountRecord['quota'] || 0);
  const last_actions = accountRecord['last_actions'] || [];
  const subscriptionRaw = (accountRecord['sub'] || "").toString();
  const subscriptionList = subscriptionRaw
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry.length > 0);
  const hasCloudSubscription = subscriptionList.length > 0;
  const CLOUD_SERVICE_DENIED_MESSAGE = "Cloud asset services are only available to paid subscribers.";
  const fieldName = event.info.fieldName;
  const requiresPaidSubscription = SUBSCRIPTION_REQUIRED_FIELDS.has(fieldName);
  const requesterCandidates = new Set([
    requester,
    owner,
    ownerSub,
    event.identity?.claims?.email,
    event.identity?.claims?.username,
    event.identity?.username,
    event.identity?.sub
  ].filter(Boolean));
  for (const candidate of Array.from(requesterCandidates)) {
    if (typeof candidate === "string") {
      const trimmed = candidate.trim();
      if (trimmed.length > 0) {
        requesterCandidates.add(trimmed);
        requesterCandidates.add(trimmed.toLowerCase());
        requesterCandidates.add(trimmed.replace(/[@.]/g, "_"));
        requesterCandidates.add(trimmed.toLowerCase().replace(/[@.]/g, "_"));
      }
    }
  }
  const isSuperUser = Array.from(requesterCandidates).some((candidate) => SUPER_USERS.has(candidate));
  const isExemptUser = Array.from(requesterCandidates).some((candidate) => EXEMPT_USERS.has(candidate));
  util.log("DEBUG", "requesterCandidates=" + JSON.stringify(Array.from(requesterCandidates)) + ", isSuperUser:" + isSuperUser.toString() + ", isExemptUser:" + isExemptUser.toString());
  util.log("DEBUG", "subscriptionRaw=" + subscriptionRaw + ", subscriptionList=" + JSON.stringify(subscriptionList) + ", hasCloudSubscription=" + hasCloudSubscription.toString() + ", accountEmail=" + (accountRecord.email || "") + ", accountStatus=" + status + ", accountQuota=" + quota.toString(), api_caller, "processEvent", logFlag);
  util.log("DEBUG", "identityEmail=" + (event.identity?.claims?.email || "") + ", identityUsername=" + (event.identity?.claims?.username || event.identity?.username || "") + ", owner=" + (owner || "") + ", ownerSub=" + (ownerSub || "") + ", fieldName=" + fieldName, api_caller, "processEvent", logFlag);
  const limitedGetAllMine = !isSuperUser && !isExemptUser && !hasCloudSubscription && fieldName === "getAllMine";
  if (!isSuperUser && !isExemptUser && !hasCloudSubscription && requiresPaidSubscription && !limitedGetAllMine) {
    util.log("ERROR", CLOUD_SERVICE_DENIED_MESSAGE + ` (User: ${requester}, field: ${fieldName}, subscriptionRaw: ${subscriptionRaw}, requesterCandidates: ${JSON.stringify(Array.from(requesterCandidates))})`, api_caller, "processEvent", logFlag);
    if (fieldName === "addAgentTasks") {
      const tasksInput = Array.isArray(event.arguments?.input) ? event.arguments.input : [event.arguments?.input].filter(Boolean);
      return tasksInput.map((task) => ({
        id: task?.id || null,
        success: false,
        error: CLOUD_SERVICE_DENIED_MESSAGE
      }));
    }
    const err = new Error(CLOUD_SERVICE_DENIED_MESSAGE);
    err.statusCode = 403;
    throw err; // AppSync will surface this as a GraphQL error instead of a type-mismatched payload
  }
  if (limitedGetAllMine) {
    returnData = {
      agents: [],
      tasks: [],
      skills: [],
      tools: [],
      knowledges: [],
      prompts: [],
      orgs: [],
      avatars: [],
      vehicles: [],
      accountInfo: accountRecord || {}
    };
    if (event && event.info && event.info.parentTypeName && event.info.fieldName) {
      return returnData;
    }
  }
  console.log("fund:", fund.toString(), " status:", status, " quota:", quota.toString(), " last actions:", JSON.stringify(last_actions));
  // get all daily summery since the begining of the month, sum up the 'busage' field. 
  // go to the account info section, get the subscription ID and product. 
  // compare the subscribed product's limit (lookup table. and get a over/under quota percentage number. )
  // combined with the subs type and inhaled  usage, check other usage and is ah;

  let overQuota = (quota > 1150);   // quote 1000 means 100% 1150 means 115% i.e. 15% over quote.

  if (((status =="active") && !overQuota) || isSuperUser || isExemptUser) {
  
    switch (event.info.parentTypeName) {
      case "Mutation":
        switch (event.info.fieldName) {
          case "addAgentTasks":
            {
              console.log(`[agentScheduler] addAgentTasks: using owner='${owner}' from identity`);
              const tasksInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const created = [];
              for (const task of tasksInput) {
                try {
                  console.log(`[agentScheduler] addAgentTasks: adding task with owner='${owner}', task.name='${task.name}'`);
                  const res = await taskService.addTask({ ...task, owner });
                  created.push({ id: res?.id || task?.id, success: res?.success !== false, error: res?.error });
                } catch (err) {
                  created.push({ id: task?.id, success: false, error: err?.message || String(err) });
                }
              }
              returnData = created;
            }
            break;
          // NOTE: getAllMine is a Query (not Mutation) - handler is in the Query switch block below
          case "addAgentSkills":
            {
              const skillsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const created = [];
              for (const skill of skillsInput) {
                try {
                  const { skill: preparedSkill, warning, error } = await hydrateSkillAssets(skill, owner);
                  if (error) {
                    created.push({ success: false, error: error.message || String(error) });
                    continue;
                  }
                  const uploadTargets = await prepareSkillUploadTargets({ skill: preparedSkill, ownerEmail: owner });
                  preparedSkill.path = uploadTargets.pathForDb || preparedSkill.path;
                  const res = await skillService.addSkill({ ...preparedSkill, owner });
                  created.push({
                    id: res.id,
                    success: res.success !== false,
                    error: res.error || warning,
                    upload_urls: uploadTargets.upload_urls
                  });
                } catch (err) {
                  created.push({ success: false, error: err.message || String(err) });
                }
              }
              returnData = created;
            }
            break;
          case "removeAgentSkills":
            {
              const skillsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const deleted = [];
              for (const skill of skillsInput) {
                const sid = typeof skill === "string" ? skill : skill?.id || skill?.skill_id;
                if (!sid) {
                  deleted.push({ success: false, error: "Missing skill id" });
                  continue;
                }
                // Pass both ownerEmail and ownerSub - deleteSkill will check ownership against both
                const res = await skillService.deleteSkill(sid, ownerEmail, ownerSub);
                deleted.push({ id: sid, success: res.success !== false, error: res.error });
              }
              returnData = deleted;
            }
            break;
          case "updateAgentSkills":
            {
              const skillsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const updated = [];
              for (const skill of skillsInput) {
                const sid = skill.id || skill.skill_id;
                if (!sid) {
                  updated.push({ success: false, error: "Missing skill id" });
                  continue;
                }
                const fields = { ...skill };
                delete fields.id;
                delete fields.skill_id;
                try {
                  const existingSkill = await skillService.getSkillById(sid);
                  const { skill: preparedFields, warning, error } = await hydrateSkillAssets(fields, owner, existingSkill);
                  if (error) {
                    updated.push({ id: sid, success: false, error: error.message || String(error) });
                    continue;
                  }
                  const skillForUploads = { ...existingSkill, ...preparedFields, id: sid };
                  const uploadTargets = await prepareSkillUploadTargets({ skill: skillForUploads, ownerEmail: owner });
                  preparedFields.path = uploadTargets.pathForDb || preparedFields.path;
                  const res = await skillService.updateSkill(sid, owner, preparedFields);
                  updated.push({
                    id: sid,
                    success: res.success !== false,
                    error: res.error || warning,
                    upload_urls: uploadTargets.upload_urls
                  });
                } catch (err) {
                  updated.push({ id: sid, success: false, error: err.message });
                }
              }
              returnData = updated;
            }
            break;
          case "addAgentTools":
            {
              const toolsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const created = [];
              for (const tool of toolsInput) {
                const res = await toolService.addTool({ ...tool, owner });
                created.push({ id: res.id, success: res.success !== false, error: res.error });
              }
              returnData = created;
            }
            break;
          case "updateAgentTools":
            {
              const toolsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const updated = [];
              for (const tool of toolsInput) {
                const tid = tool.id || tool.tool_id;
                if (!tid) {
                  updated.push({ success: false, error: "Missing tool id" });
                  continue;
                }
                const fields = { ...tool };
                delete fields.id;
                delete fields.tool_id;
                const res = await toolService.updateTool(tid, owner, fields);
                updated.push({ id: tid, success: res.success !== false, error: res.error });
              }
              returnData = updated;
            }
            break;
          case "removeAgentTools":
            {
              const toolsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const deleted = [];
              for (const tool of toolsInput) {
                const tid = typeof tool === "string" ? tool : tool?.id || tool?.tool_id;
                if (!tid) {
                  deleted.push({ success: false, error: "Missing tool id" });
                  continue;
                }
                const res = await toolService.deleteTool(tid, owner);
                deleted.push({ id: tid, success: res.success !== false, error: res.error });
              }
              returnData = deleted;
            }
            break;
          case "addAgentKnowledges":
            {
              const knowledgeInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const created = [];
              for (const kn of knowledgeInput) {
                const res = await knowledgeService.addKnowledge({ ...kn, owner });
                created.push({ id: res.id, success: res.success !== false, error: res.error });
              }
              returnData = created;
            }
            break;
          case "updateAgentKnowledges":
            {
              const knowledgeInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const updated = [];
              for (const kn of knowledgeInput) {
                const kid = kn.id || kn.knowledge_id;
                if (!kid) {
                  updated.push({ success: false, error: "Missing knowledge id" });
                  continue;
                }
                const fields = { ...kn };
                delete fields.id;
                delete fields.knowledge_id;
                const res = await knowledgeService.updateKnowledge(kid, owner, fields);
                updated.push({ id: kid, success: res.success !== false, error: res.error });
              }
              returnData = updated;
            }
            break;
          case "removeAgentKnowledges":
            {
              const knowledgeInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const deleted = [];
              for (const kn of knowledgeInput) {
                const kid = typeof kn === "string" ? kn : kn?.id || kn?.knowledge_id;
                if (!kid) {
                  deleted.push({ success: false, error: "Missing knowledge id" });
                  continue;
                }
                const res = await knowledgeService.deleteKnowledge(kid, owner);
                deleted.push({ id: kid, success: res.success !== false, error: res.error });
              }
              returnData = deleted;
            }
            break;
          case "publishAccountNotification":
            {
              const input = event.arguments.input || {};
              const ownerArg = input.owner;
              const ownerMatches = ownerArg && ownerArg === owner;
              if (!ownerMatches && !SUPER_USERS.has(owner)) {
                const err = new Error("Not authorized to publish notification for this owner");
                err.statusCode = 403;
                throw err;
              }
              const notification = {
                id: input.id || `notif_${Date.now()}`,
                owner: ownerArg,
                type: input.type || "system",
                title: input.title || "",
                message: input.message || "",
                payload: input.payload || {},
                cta_url: input.cta_url || null,
                created_at: new Date().toISOString()
              };
              returnData = notification;
            }
            break;
          case "updateAgentTasksExStatus":
            returnData = { error: "Not supported" };
            break;
          case "addVehicles":
            {
              const vehiclesInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const created = [];
              for (const veh of vehiclesInput) {
                const res = await vehicleService.addVehicle({ ...veh, owner });
                created.push({ id: res.id, success: res.success !== false });
              }
              returnData = created;
            }
            break;
          case "updateVehicles":
            {
              const vehiclesInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const updated = [];
              for (const veh of vehiclesInput) {
                const vid = veh.id || veh.vehicle_id;
                if (!vid) {
                  updated.push({ success: false, error: "Missing vehicle id" });
                  continue;
                }
                const fields = { ...veh };
                delete fields.id;
                delete fields.vehicle_id;
                const res = await vehicleService.updateVehicle(vid, owner, fields);
                updated.push({ id: vid, success: res.success !== false, error: res.error });
              }
              returnData = updated;
            }
            break;
          case "removeVehicles":
            {
              const vehiclesInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const deleted = [];
              for (const veh of vehiclesInput) {
                const vid = typeof veh === "string" ? veh : veh?.id || veh?.vehicle_id;
                if (!vid) {
                  deleted.push({ success: false, error: "Missing vehicle id" });
                  continue;
                }
                const res = await vehicleService.deleteVehicle(vid, owner);
                deleted.push({ id: vid, success: res.success !== false, error: res.error });
              }
              returnData = deleted;
            }
            break;
          case "addOrgs":
            {
              const orgsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const created = [];
              // Use Cognito sub as the owner identifier for org hierarchy
              const effectiveOwner = ownerSub || owner;
              for (const org of orgsInput) {
                // Pass owner to addOrg so it can be stored with the org
                const res = await orgService.addOrg(org, effectiveOwner);
                created.push({ id: res.id, success: res.success !== false, error: res.error });
              }
              returnData = created;
            }
            break;
          case "updateOrgs":
            {
              const orgsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const updated = [];
              for (const org of orgsInput) {
                const oid = org.id || org.org_id;
                if (!oid) {
                  updated.push({ success: false, error: "Missing org id" });
                  continue;
                }
                const fields = { ...org };
                delete fields.id;
                delete fields.org_id;
                const res = await orgService.updateOrg(oid, fields);
                updated.push({ id: oid, success: res.success !== false, error: res.error });
              }
              returnData = updated;
            }
            break;
          case "removeOrgs":
            {
              const orgsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const deleted = [];
              for (const org of orgsInput) {
                const oid = typeof org === "string" ? org : org?.id || org?.org_id;
                if (!oid) {
                  deleted.push({ success: false, error: "Missing org id" });
                  continue;
                }
                const res = await orgService.deleteOrg(oid);
                deleted.push({ id: oid, success: res.success !== false, error: res.error });
              }
              returnData = deleted;
            }
            break;
          case "addAvatarResources":
          case "addAvatars":
            {
              const avatarsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const created = [];
              for (const av of avatarsInput) {
                const avatarId = av.id || `avatar_${crypto.randomBytes(8).toString("hex")}`;
                try {
                  const prep = await prepareAvatarUploadTargets({
                    avatar: av,
                    ownerEmail: owner,
                    ownerSub,
                    generatedId: avatarId,
                    skipExistCheck: false
                  });
                  if (prep.error) {
                    created.push({ id: avatarId, success: false, error: prep.error });
                    continue;
                  }
                  const res = await avatarService.addAvatarResource({
                    ...av,
                    id: avatarId,
                    owner,
                    cloud_image_key: prep.imageKey,
                    cloud_video_key: prep.videoKey
                  });
                  created.push({
                    id: res.id,
                    success: res.success !== false,
                    error: res.error,
                    image_upload_url: prep.image_upload_url,
                    video_upload_url: prep.video_upload_url
                  });
                } catch (err) {
                  created.push({ id: avatarId, success: false, error: err.message });
                }
              }
              returnData = created;
            }
            break;
          case "updateAvatarResources":
          case "updateAvatars":
            {
              const avatarsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const updated = [];
              for (const av of avatarsInput) {
                const aid = av.id || av.avatar_id;
                if (!aid) {
                  updated.push({ success: false, error: "Missing avatar id" });
                  continue;
                }
                const fields = { ...av };
                delete fields.id;
                delete fields.avatar_id;
                try {
                  const prep = await prepareAvatarUploadTargets({
                    avatar: { ...fields, id: aid },
                    ownerEmail: owner,
                    ownerSub,
                    generatedId: aid,
                    skipExistCheck: true
                  });
                  if (!fields.cloud_image_key) {
                    fields.cloud_image_key = prep.imageKey;
                  }
                  if (!fields.cloud_video_key) {
                    fields.cloud_video_key = prep.videoKey;
                  }
                  const res = await avatarService.updateAvatarResource(aid, fields);
                  updated.push({
                    id: aid,
                    success: res.success !== false,
                    error: res.error,
                    image_upload_url: prep.image_upload_url,
                    video_upload_url: prep.video_upload_url
                  });
                } catch (err) {
                  updated.push({ id: aid, success: false, error: err.message });
                }
              }
              returnData = updated;
            }
            break;
          case "removeAvatarResources":
          case "removeAvatars":
            {
              const avatarsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const deleted = [];
              for (const av of avatarsInput) {
                const aid = typeof av === "string" ? av : av?.id || av?.avatar_id;
                if (!aid) {
                  deleted.push({ success: false, error: "Missing avatar id" });
                  continue;
                }
                const res = await avatarService.deleteAvatarResource(aid);
                deleted.push({ id: aid, success: res.success !== false, error: res.error });
              }
              returnData = deleted;
            }
            break;
          case "addPrompts":
            {
              console.log(`[agentScheduler] addPrompts: owner='${owner}', input=`, JSON.stringify(event.arguments.input));
              const promptsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const created = [];
              for (const prompt of promptsInput) {
                const effectiveOwner = owner;
                if (!effectiveOwner) {
                  console.warn(`[agentScheduler] addPrompts: Missing owner for prompt`);
                  created.push({ id: prompt.id || null, success: false, error: "Missing owner" });
                  continue;
                }
                try {
                  console.log(`[agentScheduler] addPrompts: calling promptService.addPrompt for owner='${effectiveOwner}'`);
                  const res = await promptService.addPrompt({ ...prompt, owner: effectiveOwner });
                  console.log(`[agentScheduler] addPrompts: result=`, JSON.stringify(res));
                  created.push({ id: res.id || prompt.id, success: res.success !== false, error: res.error || null });
                } catch (err) {
                  console.error(`[agentScheduler] addPrompts: error=`, err.message);
                  created.push({ id: prompt.id || null, success: false, error: err.message });
                }
              }
              console.log(`[agentScheduler] addPrompts: returning`, JSON.stringify(created));
              returnData = created;
            }
            break;
          case "updatePrompts":
            {
              const promptsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const updated = [];
              for (const prompt of promptsInput) {
                const pid = prompt.id || prompt.prompt_id;
                if (!pid) {
                  updated.push({ success: false, error: "Missing prompt id" });
                  continue;
                }
                try {
                  const fields = { ...prompt };
                  delete fields.id;
                  delete fields.prompt_id;
                  const res = await promptService.updatePrompt(pid, owner, fields);
                  updated.push({ id: pid, success: res.success !== false, error: res.error });
                } catch (err) {
                  updated.push({ id: pid, success: false, error: err.message });
                }
              }
              returnData = updated;
            }
            break;
          case "removePrompts":
            {
              const promptsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const deleted = [];
              for (const prompt of promptsInput) {
                const pid = typeof prompt === "string" ? prompt : prompt?.id || prompt?.prompt_id;
                if (!pid) {
                  deleted.push({ success: false, error: "Missing prompt id" });
                  continue;
                }
                try {
                  const res = await promptService.deletePrompt(pid, owner);
                  deleted.push({ id: pid, success: res.success !== false, error: res.error });
                } catch (err) {
                  deleted.push({ id: pid, success: false, error: err.message });
                }
              }
              returnData = deleted;
            }
            break;
          case "addAgentTools":
          case "removeAgentTools":
          case "updateAgentTools":
          case "addKnowledges":
          case "removeKnowledges":
          case "updateKnowledges":
            returnData = { error: "Not supported" };
            break;
          case "addAgents":
            {
              const agentsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const created = [];
              for (const agent of agentsInput) {
                const res = await agentService.addAgent({ ...agent, owner });
                if (res.success !== false) {
                  const agentId = res.id;
                  // Extract relationship data from extra_data
                  let extraData = agent.extra_data || {};
                  if (typeof extraData === 'string') {
                    try { extraData = JSON.parse(extraData); } catch (e) { extraData = {}; }
                  }
                  // Populate agent_org_rels
                  const orgIds = extraData.org_ids || [];
                  for (const orgId of orgIds) {
                    if (orgId) {
                      try {
                        await agentService.assignAgentToOrg(agentId, orgId, { role: 'member', status: 'active' });
                      } catch (e) {
                        console.error(`[addAgents] Failed to assign org ${orgId} to agent ${agentId}:`, e.message);
                      }
                    }
                  }
                  // Populate agent_skill_rels
                  const skillIds = extraData.skills || [];
                  for (const skillId of skillIds) {
                    if (skillId) {
                      try {
                        await agentService.assignSkillToAgent(agentId, skillId, { status: 'active' });
                      } catch (e) {
                        console.error(`[addAgents] Failed to assign skill ${skillId} to agent ${agentId}:`, e.message);
                      }
                    }
                  }
                  // Populate agent_task_rels (vehicleId can be null or from agent.vehicle_id)
                  const taskIds = extraData.tasks || [];
                  const vehicleId = agent.vehicle_id || null;
                  for (const taskId of taskIds) {
                    if (taskId) {
                      try {
                        await agentService.assignTaskToAgent(agentId, taskId, vehicleId, { status: 'pending' });
                      } catch (e) {
                        console.error(`[addAgents] Failed to assign task ${taskId} to agent ${agentId}:`, e.message);
                      }
                    }
                  }
                }
                created.push({ id: res.id, success: res.success !== false, error: res.error });
              }
              returnData = created;
            }
            break;
          case "removeAgents":
              {
                const agentsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
                const deleted = [];
                for (const agent of agentsInput) {
                  const agentId = typeof agent === "string" ? agent : agent?.id || agent?.agid || agent?.oid;
                  if (!agentId) {
                    deleted.push({ success: false, error: "Missing agent id" });
                    continue;
                  }
                  const res = await agentService.deleteAgent(agentId, owner);
                  deleted.push({ id: agentId, success: res.success !== false, error: res.error });
                }
                returnData = deleted;
              }
              break;
          case "updateAgents":
            {
              const agentsInput = Array.isArray(event.arguments.input) ? event.arguments.input : [event.arguments.input];
              const updated = [];
              for (const agent of agentsInput) {
                const agentId = agent.id || agent.agid;
                if (!agentId) {
                  updated.push({ success: false, error: "Missing agent id" });
                  continue;
                }
                const fields = { ...agent };
                delete fields.id;
                delete fields.agid;
                const res = await agentService.updateAgent(agentId, owner, fields);
                
                if (res.success !== false) {
                  // Extract relationship data from extra_data and sync relationship tables
                  let extraData = agent.extra_data || fields.extra_data || {};
                  if (typeof extraData === 'string') {
                    try { extraData = JSON.parse(extraData); } catch (e) { extraData = {}; }
                  }
                  
                  // Sync agent_org_rels - clear old and add new
                  if (extraData.org_ids !== undefined) {
                    // Clear existing org relationships for this agent
                    try {
                      const { execute } = require("./db/rdsClient");
                      await execute("DELETE FROM agent_org_rels WHERE agent_id = :agent_id", [
                        { name: "agent_id", value: { stringValue: agentId } }
                      ]);
                    } catch (e) {
                      console.error(`[updateAgents] Failed to clear org rels for agent ${agentId}:`, e.message);
                    }
                    // Add new org relationships
                    const orgIds = extraData.org_ids || [];
                    for (const orgId of orgIds) {
                      if (orgId) {
                        try {
                          await agentService.assignAgentToOrg(agentId, orgId, { role: 'member', status: 'active' });
                        } catch (e) {
                          console.error(`[updateAgents] Failed to assign org ${orgId} to agent ${agentId}:`, e.message);
                        }
                      }
                    }
                  }
                  
                  // Sync agent_skill_rels - clear old and add new
                  if (extraData.skills !== undefined) {
                    try {
                      const { execute } = require("./db/rdsClient");
                      await execute("DELETE FROM agent_skill_rels WHERE agent_id = :agent_id", [
                        { name: "agent_id", value: { stringValue: agentId } }
                      ]);
                    } catch (e) {
                      console.error(`[updateAgents] Failed to clear skill rels for agent ${agentId}:`, e.message);
                    }
                    const skillIds = extraData.skills || [];
                    for (const skillId of skillIds) {
                      if (skillId) {
                        try {
                          await agentService.assignSkillToAgent(agentId, skillId, { status: 'active' });
                        } catch (e) {
                          console.error(`[updateAgents] Failed to assign skill ${skillId} to agent ${agentId}:`, e.message);
                        }
                      }
                    }
                  }
                  
                  // Sync agent_task_rels - clear old and add new
                  if (extraData.tasks !== undefined) {
                    try {
                      const { execute } = require("./db/rdsClient");
                      await execute("DELETE FROM agent_task_rels WHERE agent_id = :agent_id", [
                        { name: "agent_id", value: { stringValue: agentId } }
                      ]);
                    } catch (e) {
                      console.error(`[updateAgents] Failed to clear task rels for agent ${agentId}:`, e.message);
                    }
                    const taskIds = extraData.tasks || [];
                    const vehicleId = agent.vehicle_id || null;
                    for (const taskId of taskIds) {
                      if (taskId) {
                        try {
                          await agentService.assignTaskToAgent(agentId, taskId, vehicleId, { status: 'pending' });
                        } catch (e) {
                          console.error(`[updateAgents] Failed to assign task ${taskId} to agent ${agentId}:`, e.message);
                        }
                      }
                    }
                  }
                }
                
                updated.push({ id: agentId, success: res.success !== false, error: res.error });
              }
              returnData = updated;
            }
            break;
          case "addAgentTools":
              // need to first check whether there is any duplicated names, platorm, app, site,  then add....
              returnData = await addAgentTools(event.arguments.input, owner, callback, logFlag, test_stub);
              //returnData = test.test_add_bots_resp;
              break;
          case "removeAgentTools":
            returnData = await removeAgentTools(event.arguments.input, callback, logFlag, test_stub);
            break;
          case "updateAgentTools":
            returnData = await updateAgentTools(event.arguments.input, owner, callback, logFlag, test_stub);
            break;
          case "addKnowledges":
              // need to first check whether there is any duplicated names, platorm, app, site,  then add....
              returnData = await addKnowledges(event.arguments.input, owner, callback, logFlag, test_stub);
              //returnData = test.test_add_bots_resp;
              break;
          case "removeKnowledges":
            returnData = await removeKnowledges(event.arguments.input, callback, logFlag, test_stub);
            break;
          case "updateKnowledges":
            returnData = await updateKnowledges(event.arguments.input, owner, callback, logFlag, test_stub);
            break;
          case "addWareHouses":
          case "addWarehouses":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              await ensureUserSkillFolders(SKILL_BUCKET, `${userDir}/`);
              const items = normalizeInputArray(event.arguments?.input);
              const results = [];
              for (let idx = 0; idx < items.length; idx++) {
                const item = items[idx];
                const id = item?.id || `wh_${Date.now()}_${idx}`;
                const now = new Date().toISOString();
                const data = { ...item, id, updated_at: now };
                if (!data.created_at) data.created_at = now;
                try {
                  await writeJsonItem(SKILL_BUCKET, `${userDir}/my_warehouses`, id, data);
                  results.push(data);
                } catch (err) {
                  console.error(`[agentScheduler] addWarehouses error for ${id}:`, err);
                  results.push({ id, name: item?.name || "", status: "error" });
                }
              }
              returnData = results;
            }
            break;
          case "UpdateWarehouses":
          case "updateWarehouses":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              const items = normalizeInputArray(event.arguments?.input);
              const results = [];
              for (let idx = 0; idx < items.length; idx++) {
                const item = items[idx];
                const wid = item?.id;
                if (!wid) {
                  results.push({ id: `wh_unknown_${idx}`, name: "", status: "error" });
                  continue;
                }
                const now = new Date().toISOString();
                const data = { ...item, id: wid, updated_at: now };
                try {
                  await writeJsonItem(SKILL_BUCKET, `${userDir}/my_warehouses`, wid, data);
                  results.push(data);
                } catch (err) {
                  console.error(`[agentScheduler] updateWarehouses error for ${wid}:`, err);
                  results.push({ id: wid, name: item?.name || "", status: "error" });
                }
              }
              returnData = results;
            }
            break;
          case "RemoveWareHouses":
          case "removeWarehouses":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              const ids = normalizeInputArray(event.arguments?.ids || event.arguments?.input);
              const results = [];
              for (const rawId of ids) {
                const wid = typeof rawId === "string" ? rawId : rawId?.id;
                if (!wid) {
                  results.push({ id: "unknown", success: false, message: "Missing id" });
                  continue;
                }
                try {
                  await deleteJsonItem(SKILL_BUCKET, `${userDir}/my_warehouses`, wid);
                  results.push({ id: wid, success: true, message: "Deleted" });
                } catch (err) {
                  console.error(`[agentScheduler] removeWarehouses error for ${wid}:`, err);
                  results.push({ id: wid, success: false, message: err.message });
                }
              }
              returnData = results;
            }
            break;
          case "addLabelFormats":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              await ensureUserSkillFolders(SKILL_BUCKET, `${userDir}/`);
              const items = normalizeInputArray(event.arguments?.input);
              const results = [];
              for (let idx = 0; idx < items.length; idx++) {
                const item = items[idx];
                const id = item?.id || `label_${Date.now()}_${idx}`;
                const now = new Date().toISOString();
                const data = { ...item, id, updated_at: now };
                if (!data.created_at) data.created_at = now;
                try {
                  await writeJsonItem(SKILL_BUCKET, `${userDir}/my_labels`, id, data);
                  results.push(data);
                } catch (err) {
                  console.error(`[agentScheduler] addLabelFormats error for ${id}:`, err);
                  results.push({ id, name: item?.name || "", status: "error" });
                }
              }
              returnData = results;
            }
            break;
          case "UpdateLabelFormats":
          case "updateLabelFormats":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              const items = normalizeInputArray(event.arguments?.input);
              const results = [];
              for (let idx = 0; idx < items.length; idx++) {
                const item = items[idx];
                const lid = item?.id;
                if (!lid) {
                  results.push({ id: `label_unknown_${idx}`, name: "", status: "error" });
                  continue;
                }
                const now = new Date().toISOString();
                const data = { ...item, id: lid, updated_at: now };
                try {
                  await writeJsonItem(SKILL_BUCKET, `${userDir}/my_labels`, lid, data);
                  results.push(data);
                } catch (err) {
                  console.error(`[agentScheduler] updateLabelFormats error for ${lid}:`, err);
                  results.push({ id: lid, name: item?.name || "", status: "error" });
                }
              }
              returnData = results;
            }
            break;
          case "RemoveLabelFormats":
          case "removeLabelFormats":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              const ids = normalizeInputArray(event.arguments?.ids || event.arguments?.input);
              const results = [];
              for (const rawId of ids) {
                const lid = typeof rawId === "string" ? rawId : rawId?.id;
                if (!lid) {
                  results.push({ id: "unknown", success: false, message: "Missing id" });
                  continue;
                }
                try {
                  await deleteJsonItem(SKILL_BUCKET, `${userDir}/my_labels`, lid);
                  results.push({ id: lid, success: true, message: "Deleted" });
                } catch (err) {
                  console.error(`[agentScheduler] removeLabelFormats error for ${lid}:`, err);
                  results.push({ id: lid, success: false, message: err.message });
                }
              }
              returnData = results;
            }
            break;
          case "addProducts":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              await ensureUserSkillFolders(SKILL_BUCKET, `${userDir}/`);
              const items = normalizeInputArray(event.arguments?.input);
              const results = [];
              for (let idx = 0; idx < items.length; idx++) {
                const item = items[idx];
                const id = item?.id || `prod_${Date.now()}_${idx}`;
                const now = new Date().toISOString();
                const data = { ...item, id, updated_at: now };
                if (!data.created_at) data.created_at = now;
                try {
                  await writeJsonItem(SKILL_BUCKET, `${userDir}/my_products`, id, data);
                  results.push(data);
                } catch (err) {
                  console.error(`[agentScheduler] addProducts error for ${id}:`, err);
                  results.push({ id, name: item?.name || "", status: "error" });
                }
              }
              returnData = results;
            }
            break;
          case "updateProducts":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              const items = normalizeInputArray(event.arguments?.input);
              const results = [];
              for (let idx = 0; idx < items.length; idx++) {
                const item = items[idx];
                const pid = item?.id;
                if (!pid) {
                  results.push({ id: `prod_unknown_${idx}`, name: "", status: "error" });
                  continue;
                }
                const now = new Date().toISOString();
                const data = { ...item, id: pid, updated_at: now };
                try {
                  await writeJsonItem(SKILL_BUCKET, `${userDir}/my_products`, pid, data);
                  results.push(data);
                } catch (err) {
                  console.error(`[agentScheduler] updateProducts error for ${pid}:`, err);
                  results.push({ id: pid, name: item?.name || "", status: "error" });
                }
              }
              returnData = results;
            }
            break;
          case "removeProducts":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              const ids = normalizeInputArray(event.arguments?.ids || event.arguments?.input);
              const results = [];
              for (const rawId of ids) {
                const pid = typeof rawId === "string" ? rawId : rawId?.id;
                if (!pid) {
                  results.push({ id: "unknown", success: false, message: "Missing id" });
                  continue;
                }
                try {
                  await deleteJsonItem(SKILL_BUCKET, `${userDir}/my_products`, pid);
                  results.push({ id: pid, success: true, message: "Deleted" });
                } catch (err) {
                  console.error(`[agentScheduler] removeProducts error for ${pid}:`, err);
                  results.push({ id: pid, success: false, message: err.message });
                }
              }
              returnData = results;
            }
            break;
          case "addInventories":
            {
              const items = normalizeInputArray(event.arguments?.input);
              returnData = items.map((item, idx) => ({
                id: placeholderId("inv", item?.id, idx),
                success: true,
                message: "placeholder"
              }));
            }
            break;
          case "updateInventories":
            {
              const items = normalizeInputArray(event.arguments?.input);
              returnData = items.map((item, idx) => {
                const iid = item?.id || (typeof item === "string" ? item : null);
                if (!iid) {
                  return { id: placeholderId("inv", null, idx), success: false, message: "Missing inventory id" };
                }
                return { id: iid, success: true, message: "placeholder" };
              });
            }
            break;
          case "removeInventories":
            {
              const items = normalizeInputArray(event.arguments?.input);
              returnData = items.map((item, idx) => {
                const iid = typeof item === "string" ? item : item?.id;
                if (!iid) {
                  return { id: placeholderId("inv", null, idx), success: false, message: "Missing inventory id" };
                }
                return { id: iid, success: true, message: "placeholder" };
              });
            }
            break;
          case "saveSkillFile":
            {
              returnData = await skillEditorService.saveSkillFile(event.arguments?.input || {});
            }
            break;
          case "writeSkillFile":
            {
              returnData = await skillEditorService.writeSkillFile(event.arguments?.input || {});
            }
            break;
          case "scaffoldSkill":
            {
              returnData = await skillEditorService.scaffoldSkill(event.arguments?.input || {});
            }
            break;
          case "copySkillTo":
            {
              returnData = await skillEditorService.copySkillTo(event.arguments?.input || {});
            }
            break;
          case "saveEditorCache":
            {
              returnData = await skillEditorService.saveEditorCache(event.arguments?.input || {});
            }
            break;
          case "clearEditorCache":
            {
              returnData = await skillEditorService.clearEditorCache(event.arguments?.userId || "");
            }
            break;
          case "runSkill":
            {
              returnData = await skillEditorService.runSkill(event.arguments?.input || {});
            }
            break;
          case "pauseRunSkill":
            {
              returnData = await skillEditorService.pauseRunSkill(event.arguments?.input || {});
            }
            break;
          case "resumeRunSkill":
            {
              returnData = await skillEditorService.resumeRunSkill(event.arguments?.input || {});
            }
            break;
          case "stepRunSkill":
            {
              returnData = await skillEditorService.stepRunSkill(event.arguments?.input || {});
            }
            break;
          case "cancelRunSkill":
            {
              returnData = await skillEditorService.cancelRunSkill(event.arguments?.input || {});
            }
            break;
          case "setupSimStep":
            {
              returnData = await skillEditorService.setupSimStep(event.arguments?.bundle || event.arguments?.input || null);
            }
            break;
          case "stepSim":
            {
              returnData = await skillEditorService.stepSim();
            }
            break;
          case "testLanggraph2Flowgram":
            {
              returnData = await skillEditorService.testLanggraph2Flowgram();
            }
            break;
          case "simTimerEvent":
            {
              returnData = await skillEditorService.simTimerEvent();
            }
            break;
          case "simWebsocketEvent":
            {
              returnData = await skillEditorService.simWebsocketEvent();
            }
            break;
          case "simSseEvent":
            {
              returnData = await skillEditorService.simSseEvent();
            }
            break;
          case "simWebhookEvent":
            {
              returnData = await skillEditorService.simWebhookEvent();
            }
            break;
          case "setSkillBreakpoints":
            {
              returnData = await skillEditorService.setSkillBreakpoints(event.arguments?.username || "", event.arguments?.node_name || "");
            }
            break;
          case "clearSkillBreakpoints":
            {
              returnData = await skillEditorService.clearSkillBreakpoints(event.arguments?.username || "", event.arguments?.node_name || "");
            }
            break;
          case "requestSkillState":
            {
              returnData = await skillEditorService.requestSkillState(event.arguments?.username || "", event.arguments?.skill || {});
            }
            break;
          case "injectSkillState":
            {
              returnData = await skillEditorService.injectSkillState(event.arguments?.username || "", event.arguments?.skill || {});
            }
            break;
          case "loadSkillSchemas":
            {
              returnData = await skillEditorService.loadSkillSchemas(event.arguments?.username || "", event.arguments?.skill || {});
            }
            break;
          case "createSkillEditorChatSession":
            {
              returnData = await skillEditorService.createSkillEditorChatSession(event.arguments?.input || {});
            }
            break;
          case "sendSkillEditorChatMessage":
            {
              returnData = await skillEditorService.sendSkillEditorChatMessage(event.arguments?.input || {});
            }
            break;
          case "cancelSkillEditorChatGeneration":
            {
              returnData = await skillEditorService.cancelSkillEditorChatGeneration(event.arguments?.sessionId || "");
            }
            break;
          case "deleteSkillEditorChatSession":
            {
              returnData = await skillEditorService.deleteSkillEditorChatSession(event.arguments?.sessionId || "");
            }
            break;
          case "updateSettings":
            {
              // Upsert settings into DynamoDB ECAN_Settings table
              const input = event.arguments?.input;

              // input is [AWSJSON] — first element contains the settings payload
              let payload = {};
              if (Array.isArray(input) && input.length > 0) {
                payload = typeof input[0] === "string" ? JSON.parse(input[0]) : input[0];
              } else if (typeof input === "string") {
                payload = JSON.parse(input);
              } else if (typeof input === "object" && input !== null) {
                payload = input;
              }

              // Use username from payload (consistent with getSettings which uses event.arguments.username)
              const settingsOwnerU = normalizeEmailForPath(payload.username || ownerEmail || owner);
              console.log(`[agentScheduler] updateSettings: owner=${settingsOwnerU}`);

              // Check if user already has a settings record to preserve sid
              const existing = await settingsService.getSettingsByOwner(settingsOwnerU);
              const existingSid = existing ? existing.sid : null;

              // Build the upsert payload — separate general settings from providers
              // The frontend sends flat form values: { username, schedule_mode, debug_mode, default_llm, ... }
              // Extract providers if present, treat the rest as general settings
              const { llm_providers, embedding_providers, rerank_providers, username: _u, ...generalFields } = payload;

              const upsertPayload = {
                settings: payload.settings || payload.general_settings || generalFields || {},
                llm_providers: llm_providers || (existing ? existing.llm_providers : {}),
                embedding_providers: embedding_providers || (existing ? existing.embedding_providers : {}),
                rerank_providers: rerank_providers || (existing ? existing.rerank_providers : {}),
              };

              const result = await settingsService.upsertSettings(settingsOwnerU, upsertPayload, existingSid);
              console.log(`[agentScheduler] updateSettings: upserted sid=${result.sid}`);
              returnData = { success: true, sid: result.sid };
            }
            break;
          default:
            return UNRECOGNIZED_INPUT;
        }
        break;
      case "Query":
        util.log("DEBUG", "processing query....", api_caller, "processEvent", logFlag);

        switch (event.info.fieldName) {
          case "getAgents":
            {
              const agents = await agentService.getAgentsByOwner(owner);
              returnData = agents;
            }
            break;
          case "getAgentSkills":
              {
                // Query skills by both email and Cognito sub to handle legacy and new data
                console.log(`[agentScheduler] getAgentSkills: querying for ownerEmail='${ownerEmail}', ownerSub='${ownerSub}'`);
                const skills = await skillService.getSkillsByOwners(ownerEmail, ownerSub);
                returnData = skills;
              }
              break;
          case "getAgentTasks":
            {
              // Query tasks by both email and Cognito sub to handle legacy and new data
              console.log(`[agentScheduler] getAgentTasks: querying for ownerEmail='${ownerEmail}', ownerSub='${ownerSub}'`);
              const tasks = await taskService.getTasksByOwners(ownerEmail, ownerSub);
              returnData = tasks;
            }
            break;
          case "getAgentTools":
            {
              const tools = await toolService.getToolsByOwner(owner);
              returnData = tools;
            }
            break;
          case "getAgentKnowledges":
            {
              const knowledges = await knowledgeService.getKnowledgesByOwner(owner);
              returnData = knowledges;
            }
            break;
          case "getKnowledges":
            returnData = { error: "Not supported" };
            break;
          case "queryAgents":
            util.log("DEBUG", "querying bots....!", api_caller, "processEvent", logFlag);
            {
              const qArg = event.arguments?.qa || event.arguments?.qb || event.arguments?.query || {};
              const result = await agentService.queryAgents({
                id: qArg.id,
                name: qArg.name,
                description: qArg.description
              });
              returnData = result;
            }
            break;
          case "queryAgentSkills":
              util.log("DEBUG", "querying skills....!", api_caller, "processEvent", logFlag);
              {
                const qArg = event.arguments?.qs || {};
                const result = await skillService.querySkills({
                  id: qArg.id,
                  name: qArg.name,
                  description: qArg.description
                });
                returnData = result;
              }
              break;
          case "queryAgentTasks":
            util.log("DEBUG", "querying missions....!", api_caller, "processEvent", logFlag);
            {
              const qArg = event.arguments?.qm?.[0] || event.arguments?.qm || {};
              const result = await taskService.queryTasks({
                id: qArg.id,
                name: qArg.name,
                description: qArg.description
              });
              const filtered = owner ? result.filter(t => t.owner === owner) : result;
              returnData = filtered;
            }
            break;
          case "queryAgentTools":
            util.log("DEBUG", "querying tools....!", api_caller, "processEvent", logFlag);
            {
              const qArg = event.arguments?.input || event.arguments?.qt || {};
              const result = await toolService.queryTools({
                id: qArg.id,
                name: qArg.name,
                description: qArg.description
              });
              const filtered = owner ? result.filter(t => t.owner === owner) : result;
              returnData = filtered;
            }
            break;
          case "queryAgentKnowledges":
            util.log("DEBUG", "querying knowledges....!", api_caller, "processEvent", logFlag);
            {
              const qArg = event.arguments?.input || event.arguments?.qk || {};
              const result = await knowledgeService.queryKnowledges({
                id: qArg.id,
                name: qArg.name,
                description: qArg.description
              });
              const filtered = owner ? result.filter(k => k.owner === owner) : result;
              returnData = filtered;
            }
            break;
          case "queryKnowledges":
              util.log("DEBUG", "querying knowledges....!", api_caller, "processEvent", logFlag);
              returnData = { error: "Not supported" };
              break;
          case "getVehicles":
            {
              const vehicles = await vehicleService.queryVehicles({ id: null, name: null, description: null });
              const owned = vehicles.filter(v => v.owner === owner);
              returnData = owned;
            }
            break;
          case "getPrompts":
            {
              const requestedOwner = event.arguments?.owner;
              const ownerFilter = requestedOwner === owner ? requestedOwner : owner;
              const prompts = await promptService.listPrompts(ownerFilter);
              returnData = prompts;
            }
            break;
          case "queryVehicles":
            {
              const qArg = event.arguments?.qv || {};
              const result = await vehicleService.queryVehicles({
                id: qArg.id,
                name: qArg.name,
                description: qArg.description
              });
              const filtered = owner ? result.filter(v => v.owner === owner) : result;
              returnData = filtered;
            }
            break;
          case "queryPrompts":
            {
              const qArg = event.arguments?.input || {};
              const requestedOwner = qArg.owner;
              // Only allow querying your own prompts; fall back to caller owner if mismatched
              const ownerFilter = requestedOwner === owner ? requestedOwner : owner;
              try {
                const result = await promptService.queryPrompts({
                  id: qArg.id,
                  owner: ownerFilter,
                  version: qArg.version,
                  search: qArg.search
                });
                returnData = Array.isArray(result) ? result : [];
              } catch (err) {
                util.log("ERROR", "queryPrompts failed: " + err.message, api_caller, "processEvent", logFlag);
                // Return empty list to satisfy non-nullable list return type
                returnData = [];
              }
            }
            break;
          case "getOrgs":
            {
              const orgs = await orgService.getAllOrgs();
              returnData = orgs;
            }
            break;
          case "getWarehouses":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              await ensureUserSkillFolders(SKILL_BUCKET, `${userDir}/`);
              const userWarehouses = await readJsonDir(SKILL_BUCKET, `${userDir}/my_warehouses/`);
              // Pack non-schema fields into notes as JSON for AppSync compatibility
              const WH_SCHEMA_FIELDS = new Set(["address","code","contact_name","contact_phone","created_at","id","name","notes","status","updated_at"]);
              for (const w of userWarehouses) {
                if (!w.id) w.id = (w._filename || "").replace(".json", "");
                const extra = {};
                for (const key of Object.keys(w)) {
                  if (!WH_SCHEMA_FIELDS.has(key)) extra[key] = w[key];
                }
                if (Object.keys(extra).length > 0) w.notes = JSON.stringify(extra);
              }
              returnData = userWarehouses;
            }
            break;
          case "queryWarehouses":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              const userWarehouses = await readJsonDir(SKILL_BUCKET, `${userDir}/my_warehouses/`);
              const WH_SCHEMA_FIELDS_Q = new Set(["address","code","contact_name","contact_phone","created_at","id","name","notes","status","updated_at"]);
              for (const w of userWarehouses) {
                if (!w.id) w.id = (w._filename || "").replace(".json", "");
                const extra = {};
                for (const key of Object.keys(w)) {
                  if (!WH_SCHEMA_FIELDS_Q.has(key)) extra[key] = w[key];
                }
                if (Object.keys(extra).length > 0) w.notes = JSON.stringify(extra);
              }
              returnData = userWarehouses;
            }
            break;
          case "getWarehouse":
            {
              const id = event.arguments?.id || event.arguments?.input?.id;
              returnData = buildWarehousePlaceholder({ id }, 0);
            }
            break;
          case "getNodeStateSchema":
            {
              returnData = await skillEditorService.getNodeStateSchema();
            }
            break;
          case "readSkillFile":
            {
              returnData = await skillEditorService.readSkillFile(event.arguments?.filePath || "");
            }
            break;
          case "openSkillFile":
            {
              returnData = await skillEditorService.openSkillFile(event.arguments?.filePath || "", event.arguments?.skillName || null);
            }
            break;
          case "listSkillFiles":
            {
              returnData = await skillEditorService.listSkillFiles(
                event.arguments?.prefix || "",
                event.arguments?.limit ?? null,
                event.arguments?.nextToken || null
              );
            }
            break;
          case "checkSkillExists":
            {
              returnData = await skillEditorService.checkSkillExists(event.arguments?.name || "");
            }
            break;
          case "getEditorCache":
            {
              returnData = await skillEditorService.getEditorCache(event.arguments?.userId || "");
            }
            break;
          case "getSkillRunStatus":
            {
              returnData = await skillEditorService.getSkillRunStatus(event.arguments?.runId || "", event.arguments?.since || null);
            }
            break;
          case "getSkillEditorEvents":
            {
              returnData = await skillEditorService.getSkillEditorEvents(event.arguments?.sessionId || "", event.arguments?.since || null);
            }
            break;
          case "getSkillEditorChatSessions":
            {
              returnData = await skillEditorService.getSkillEditorChatSessions(event.arguments?.userId || "");
            }
            break;
          case "getSkillEditorChatHistory":
            {
              returnData = await skillEditorService.getSkillEditorChatHistory(
                event.arguments?.sessionId || "",
                event.arguments?.limit ?? null,
                event.arguments?.offset ?? null
              );
            }
            break;
          case "getLabelFormats":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              await ensureUserSkillFolders(SKILL_BUCKET, `${userDir}/`);
              // Read public (system) templates + user's own
              const [systemLabels, userLabels] = await Promise.all([
                readJsonDir(SKILL_BUCKET, "public/labels/"),
                readJsonDir(SKILL_BUCKET, `${userDir}/my_labels/`)
              ]);
              for (const l of systemLabels) {
                if (!l.id) l.id = (l._filename || "").replace(".json", "");
                l._source = "system";
              }
              for (const l of userLabels) {
                if (!l.id) l.id = (l._filename || "").replace(".json", "");
                l._source = "user";
              }
              // Pack non-schema fields into settings AWSJSON for AppSync compatibility
              // AWSJSON fields must be a JSON string for Lambda resolvers
              const LABEL_SCHEMA_FIELDS = new Set(["carrier","created_at","dpi","id","name","service","settings","size","status","template_url","updated_at"]);
              const allLabels = [...systemLabels, ...userLabels];
              for (const item of allLabels) {
                const extra = {};
                for (const key of Object.keys(item)) {
                  if (!LABEL_SCHEMA_FIELDS.has(key)) {
                    extra[key] = item[key];
                  }
                }
                // AppSync AWSJSON: Lambda must return a raw JSON string.
                // JSON.stringify once is correct — AppSync will NOT re-encode it.
                // The issue was the client receiving double-escaped strings.
                // Use the raw object instead: AppSync will serialize it for us.
                item.settings = extra;
              }
              returnData = allLabels;
            }
            break;
          case "queryLabelFormats":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              const [systemLabels, userLabels] = await Promise.all([
                readJsonDir(SKILL_BUCKET, "public/labels/"),
                readJsonDir(SKILL_BUCKET, `${userDir}/my_labels/`)
              ]);
              for (const l of systemLabels) { if (!l.id) l.id = (l._filename || "").replace(".json", ""); l._source = "system"; }
              for (const l of userLabels) { if (!l.id) l.id = (l._filename || "").replace(".json", ""); l._source = "user"; }
              // Pack non-schema fields into settings AWSJSON
              const LABEL_SCHEMA_FIELDS_Q = new Set(["carrier","created_at","dpi","id","name","service","settings","size","status","template_url","updated_at"]);
              const allLabelsQ = [...systemLabels, ...userLabels];
              for (const item of allLabelsQ) {
                const extra = {};
                for (const key of Object.keys(item)) {
                  if (!LABEL_SCHEMA_FIELDS_Q.has(key)) {
                    extra[key] = item[key];
                  }
                }
                item.settings = extra;
              }
              returnData = allLabelsQ;
            }
            break;
          case "getLabelFormat":
            {
              const id = event.arguments?.id || event.arguments?.input?.id;
              returnData = buildLabelFormatPlaceholder({ id }, 0);
            }
            break;
          case "getProducts":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              await ensureUserSkillFolders(SKILL_BUCKET, `${userDir}/`);
              const userProducts = await readJsonDir(SKILL_BUCKET, `${userDir}/my_products/`);
              // Pack non-schema fields into attributes AWSJSON
              const PRODUCT_SCHEMA_FIELDS = new Set(["attributes","barcode","created_at","description","dimensions_cm","id","name","sku","status","updated_at","weight_grams"]);
              for (const p of userProducts) {
                if (!p.id) p.id = (p._filename || "").replace(".json", "");
                const extra = {};
                for (const key of Object.keys(p)) {
                  if (!PRODUCT_SCHEMA_FIELDS.has(key)) extra[key] = p[key];
                }
                p.attributes = extra;
              }
              returnData = userProducts;
            }
            break;
          case "queryProducts":
            {
              const userDir = normalizeEmailForPath(ownerEmail || owner);
              const userProducts = await readJsonDir(SKILL_BUCKET, `${userDir}/my_products/`);
              const PRODUCT_SCHEMA_FIELDS_Q = new Set(["attributes","barcode","created_at","description","dimensions_cm","id","name","sku","status","updated_at","weight_grams"]);
              for (const p of userProducts) {
                if (!p.id) p.id = (p._filename || "").replace(".json", "");
                const extra = {};
                for (const key of Object.keys(p)) {
                  if (!PRODUCT_SCHEMA_FIELDS_Q.has(key)) extra[key] = p[key];
                }
                p.attributes = extra;
              }
              returnData = userProducts;
            }
            break;
          case "getProduct":
            {
              const id = event.arguments?.id || event.arguments?.input?.id;
              returnData = buildProductPlaceholder({ id }, 0);
            }
            break;
          case "getInventories":
            {
              returnData = [];
            }
            break;
          case "queryInventories":
            {
              returnData = [];
            }
            break;
          case "getInventory":
            {
              const id = event.arguments?.id || event.arguments?.input?.id;
              returnData = buildInventoryPlaceholder({ id }, 0);
            }
            break;
          case "queryOrgs":
            {
              const qArg = event.arguments?.qo || {};
              const result = await orgService.searchOrgs({
                name: qArg.name,
                org_type: qArg.org_type,
                status: qArg.status
              });
              returnData = result;
            }
            break;
          case "getOrgTree":
            {
              const rootId = event.arguments?.root_id || null;
              const result = await orgService.getOrgTree(rootId);
              returnData = result.data || result;
            }
            break;
          case "getOrgAgentTree":
              {
                const rootId = event.arguments?.root_id || null;
                // Get username from arguments - this contains the sanitized email (e.g., songc_yahoo_com)
                const argUsername = event.arguments?.username || null;
                const result = await getOrgAgentTree(rootId, owner, ownerSub, ownerEmail, argUsername);
                returnData = result;
              }
              break;
          case "getAvatarResources":
          case "getAvatars":
            {
              // Return both public (system) avatars and user's own avatars
              const [publicAvatars, userAvatars] = await Promise.all([
                avatarService.getAvatarResourcesByOwner("public"),
                avatarService.getAvatarResourcesByOwner(owner)
              ]);
              returnData = await presignAvatarRecords([...publicAvatars, ...userAvatars]);
            }
            break;
          case "getSettings":
            {
              // Try DynamoDB first (ECAN_Settings table)
              // Prefer explicit username argument (Cognito access token may not have email in claims)
              const settingsOwnerRaw = event.arguments?.username || ownerEmail || owner;
              const settingsOwner = normalizeEmailForPath(settingsOwnerRaw);
              console.log(`[agentScheduler] getSettings: querying DynamoDB for owner=${settingsOwner}`);
              const dbSettings = await settingsService.getSettingsByOwner(settingsOwner);

              if (dbSettings) {
                console.log(`[agentScheduler] getSettings: found DynamoDB record sid=${dbSettings.sid}`);
                returnData = dbSettings;
              } else {
                // Fallback: read from S3 (legacy)
                console.log(`[agentScheduler] getSettings: no DynamoDB record, falling back to S3`);
                const userPrefix = `${settingsOwner}/`;
                const settingsKey = `${userPrefix}settings/settings.json`;

                if (!(await objectExists(SKILL_BUCKET, settingsKey))) {
                  await ensureUserSkillFolders(SKILL_BUCKET, userPrefix);
                  const copied = await copyPublicSettingsToUser(SKILL_BUCKET, userPrefix);
                  if (!copied) {
                    await s3.send(new PutObjectCommand({
                      Bucket: SKILL_BUCKET,
                      Key: settingsKey,
                      Body: JSON.stringify({})
                    }));
                  }
                }

                const settings = await loadUserSettings(SKILL_BUCKET, settingsKey);
                returnData = { settings };
              }
            }
            break;
          case "getAllMine":
            {
              // Query using both ownerEmail and ownerSub to find resources stored with either identifier
              console.log(`[agentScheduler] getAllMine (Query): loading all mine for ownerEmail='${ownerEmail}', ownerSub='${ownerSub}'`);
              const safeList = async (label, fn) => {
                try {
                  const result = await fn();
                  return Array.isArray(result) ? result : [];
                } catch (err) {
                  util.log("ERROR", `getAllMine ${label} failed: ${err.message}`, api_caller, "processEvent", logFlag);
                  return [];
                }
              };

              // Query agents by username, email, and Cognito sub to handle all possible owner formats
              const agents = await safeList("agents", () => agentService.getAgentsByOwners(owner, ownerEmail, ownerSub));
              // Query skills by both email and Cognito sub to handle legacy and new data
              const skills = await safeList("skills", () => skillService.getSkillsByOwners(ownerEmail, ownerSub));
              // Query tasks by both email and Cognito sub to handle legacy and new data
              const tasks = await safeList("tasks", () => taskService.getTasksByOwners(ownerEmail, ownerSub));
              const tools = await safeList("tools", () => toolService.getToolsByOwner(owner));
              const knowledges = await safeList("knowledges", () => knowledgeService.getKnowledgesByOwner(owner));
              const prompts = await safeList("prompts", () => promptService.listPrompts(owner));
              
              // Get or create the user's org tree (using Cognito sub as owner identifier)
              // This ensures each user has their own organization hierarchy
              const orgs = await safeList("orgs", async () => {
                // ownerSub is the Cognito sub ID - use it to find/create user's root org
                const effectiveOwner = ownerSub || owner;
                if (effectiveOwner) {
                  // Get the user's org tree (creates root if doesn't exist)
                  const treeResult = await orgService.getOrgTreeByOwner(effectiveOwner);
                  if (treeResult.success && treeResult.data) {
                    // Flatten tree to array for getAllMine response
                    const flattenTree = (node, arr = []) => {
                      arr.push(node);
                      if (node.children) {
                        for (const child of node.children) {
                          flattenTree(child, arr);
                        }
                      }
                      return arr;
                    };
                    return flattenTree(treeResult.data);
                  }
                }
                // Fallback to empty array
                return [];
              });
              
              const avatars = await safeList("avatars", async () => {
                // Include both public (system) avatars and user's own avatars
                const [publicAvatars, userAvatars] = await Promise.all([
                  avatarService.getAvatarResourcesByOwner("public"),
                  avatarService.getAvatarResourcesByOwner(owner)
                ]);
                return presignAvatarRecords([...publicAvatars, ...userAvatars]);
              });
              const vehicles = await safeList("vehicles", async () => {
                const all = await vehicleService.queryVehicles({ id: null, name: null, description: null });
                return owner ? all.filter(v => v.owner === owner) : all;
              });

              // Load user settings from DynamoDB
              let userSettings = null;
              try {
                const settingsOwnerAll = normalizeEmailForPath(owner);
                const dbSettingsAll = await settingsService.getSettingsByOwner(settingsOwnerAll);
                if (dbSettingsAll) {
                  userSettings = dbSettingsAll;
                  console.log(`[agentScheduler] getAllMine: loaded settings sid=${dbSettingsAll.sid}`);
                }
              } catch (err) {
                util.log("ERROR", `getAllMine settings failed: ${err.message}`, api_caller, "processEvent", logFlag);
              }

              returnData = {
                agents,
                tasks,
                skills,
                tools,
                knowledges,
                prompts,
                orgs,
                avatars,
                vehicles,
                accountInfo: accountRecord,
                settings: userSettings
              };
            }
            break;
          case "queryAvatarResources":
          case "queryAvatars":
            {
              // Accept input: AvatarQueryInput (schema) OR legacy qb/qa string
              let qArg = event.arguments?.input || event.arguments?.qb || event.arguments?.qa || {};
              if (typeof qArg === "string") {
                try { qArg = JSON.parse(qArg); } catch (_e) { qArg = {}; }
              }
              const ownerFilter = qArg.owner || owner;
              const avatars = await avatarService.getAvatarResourcesByOwner(ownerFilter, qArg.resource_type);
              returnData = await presignAvatarRecords(avatars);
            }
            break;
          default:
            returnData = UNRECOGNIZED_INPUT;
        }
        break;
    } 
  } else {
    const requestedField = event?.info?.fieldName;
    if (requestedField === "getAllMine") {
      returnData = {
        agents: [],
        tasks: [],
        skills: [],
        tools: [],
        knowledges: [],
        prompts: [],
        orgs: [],
        avatars: [],
        vehicles: [],
        accountInfo: accountRecord || {},
        settings: null
      };
    } else {
      returnData = { error: "ACCOUNT INSUFFICIENT" };
    }
  }

  // TODO implement
  // For AppSync direct Lambda resolvers, return the raw data (must match GraphQL type).
  if (event && event.info && event.info.parentTypeName && event.info.fieldName) {
    return returnData;
  }

  // Fallback for other invokers that expect an API Gateway–style response
  return {
    statusCode: statCode,
    body: returnData
  };
}


process.on('uncaughtException', (error) => {
  console.error('Uncaught Exception:', error.message);
  console.error('Stack trace:', error.stack);
});

//now the main program...
exports.handler = async (event, context, callback) => {
  var resp;
  var expression;
  var uto;
  var i;
  var eq;
  var ctc;
  var default_ts = {"testmode": false};
  var entranceInfo;
  var lamb_result  = {reqId:context.awsRequestId, error: false, cause: ""};
  console.log("event: " + JSON.stringify(event));
  
  // there are two ways this can be called? 1) with cognito authorization 2) self-generated api key authorization
  if (event.identity && ('claims' in event.identity) && ('sourceIp' in event.identity)) {
    entranceInfo= {email:event.identity.claims.email, ip:event.identity.sourceIp, input:event.info.fieldName, reqId:context.awsRequestId};
  } else if (event.request && event.request.headers) {
    
    entranceInfo= {email:event.request.headers['x-api-caller'], ip:event.request.headers['x-client-ip'], input:event.info.fieldName, reqId:context.awsRequestId};
  } else {
    entranceInfo= {email:'unknown', ip:'unknown', input:event.info?.fieldName || 'unknown', reqId:context.awsRequestId};
  }

  console.log("entrance: " + JSON.stringify(entranceInfo));
  
  var settings;

  try {
    // Assuming your EFS is mounted at /mnt/myefs and node_modules is at the root
    const efsNodeModulesPath = '/mnt/efs/access/layers/usefull0/node_modules';
    
    // Get the existing NODE_PATH
    const existingNodePath = process.env.NODE_PATH || '';
    
    // Set the new NODE_PATH
    process.env.NODE_PATH = `${existingNodePath}:${efsNodeModulesPath}`;
    
    // Requiring the module to refresh the paths
    require('module').Module._initPaths();
  
    // util.log("entrance: ", JSON.stringify(entranceInfo), api_caller, "main", logFlag);
    
    util.log("Inside Lambda: ", JSON.stringify(event), api_caller, "main", logFlag);
    if (event.hasOwnProperty('testmode')) {
      // doing all unit tests here.
      util.log("DEBUG", "Event test mode...", api_caller, "main", logFlag);
      for (var tc of ut.testcases) {
        if (!tc["skip"]) {
          util.log("DEBUG", "no skipping: " + JSON.stringify(tc), api_caller, "main", logFlag);
          
          expression = tc["function"] + "(";
          i = 0;
          for (var carg of tc["arguments"]) {
            // util.log("carg:", carg, api_caller, "main", logFlag);
            if ((typeof carg) == "string") {
              expression = expression + "\"";
            }
            
            if ((typeof carg) == "object") {
              if (carg.constructor.name == "Date") {
                eval("arg" + i.toString() + " = carg");
                expression = expression + "arg" + i.toString() ;
              } else {
                expression = expression + JSON.stringify(carg);
              }
            } else {
              expression = expression + carg;
            }
            
            if ((typeof carg) == "string") {
              expression = expression + "\"";
            }
            
            if (i !=  (tc["arguments"].length -1) ) {
              expression = expression + ", ";
            }
            
            i = i + 1;
          }
          
          expression = expression + ");";
          util.log("evaluating: ", expression, api_caller, "main", logFlag);
          
          if (tc.hasOwnProperty('functype')) {
            if (tc["functype"] == "asyn") {
              util.log("DEBUG", "evaluating async......", api_caller, "main", logFlag);
              // let asynScript = '(async () => {await ' + expression + '; script_ended = true; })();';
              uto = await eval("(async () => {await " + expression + "})()");
  
              // uto = eval(asynScript);
            } else {
              uto = eval(expression);
            }
          } else {
            uto = eval(expression);
          }
          
          //util.log("DEBUG", uto, tc["expected"], api_caller, "main", logFlag);
          
          if (tc["expected"].constructor.name == "Date") {
            if ((uto.getFullYear() != tc["expected"].getFullYear()) || (uto.getMonth() != tc["expected"].getMonth()) || (uto.getDate() != tc["expected"].getDate())) {
              eq = false;
            }
          } else {
            eq = util.objEqual(uto, tc["expected"]);
          }
          if (eq == true) {
            util.log("TEST ", tc["number"] + " : " + tc["function"] + " Succeeded!", api_caller, "main", logFlag);
          } else {
            util.log("TEST ", tc["number"] + " : " + tc["function"] + " Failed!", api_caller, "main", logFlag);
            util.log("evaluating: ", expression, api_caller, "main", logFlag);
            
            if ((typeof uto) == "object") {
              if (carg.constructor.name == "Date") {
                util.log("DEBUG", uto.toISOString() + "<-->" + tc["expected"].toISOString(), api_caller, "main", logFlag);
              } else {
                util.log("DEBUG", JSON.stringify(uto) + "<-->" + JSON.stringify(tc["expected"]), api_caller, "main", logFlag);
              }
            } else if ((typeof uto) == "undefined") {
              util.log("DEBUG", "undefined " + "<-->" + tc["expected"].toString(), api_caller, "main", logFlag);
            } else if ((typeof uto) == "string") {
              util.log("DEBUG", uto + "<-->" + tc["expected"], api_caller, "main", logFlag);
            } else {
              util.log("DEBUG", uto.toString() + "<-->" + tc["expected"].toString(), api_caller, "main", logFlag);
            }
    
          }
        }
      }
        
    } else {
      util.log("DEBUG", "Event non test mode...", api_caller, "main", logFlag);
  
      if (event["arguments"].hasOwnProperty('settings')) {
        if  (event["arguments"]["settings"].hasOwnProperty('testmode')) {
          settings = event["arguments"]["settings"];
        }
      } else {
        settings = {"testmode": false};
      }
      
      if (settings.hasOwnProperty('use_cloud_test_cases')) {
        if (settings["testmode_cloud"] == true) {
          util.log("DEBUG", "Event Argument test mode...", settings, api_caller, "main", logFlag);
    
          ctc = ut.testcases.find((obj) => obj["number"] === settings["test_name"]);
          resp = {
            statusCode: statCode,
            body: lzstring.compressToBase64(JSON.stringify(ctc["expected"]))
          };
        }
      } else {
        if (settings["testmode_cloud"] == true) {
          default_ts = settings["test_stub"];
        }
        util.log("DEBUG", "test stub is..."+JSON.stringify(default_ts), api_caller, "main", logFlag);
        resp = await processEvent(event, context, callback, default_ts);
        // resp.body = lzstring.compressToBase64(JSON.stringify(result))
  
      } 
      var respLog = {result: statCode, error: errMsg+"!"};
      util.log("DEBUG", "response: " + JSON.stringify(resp), api_caller, "main", logFlag);
      
    }
  } catch (error) {
    lamb_result.error = true;
    lamb_result.cause = error.toString();
    console.error('Error occurred:', error.message);
    console.error('Stack trace:', error.stack);
  }
  
  
  console.log("Lambda Result :", JSON.stringify(lamb_result));

  
  return resp;

};
