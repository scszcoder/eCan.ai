/**
 * Messaging service — outbound SMS and email.
 *
 * Outbound SMS: AWS End User Messaging SMS (formerly Pinpoint SMS) via
 *   pinpoint-sms-voice-v2 SDK. Requires an OriginationIdentity (a phone
 *   number ARN, pool ID, or registered sender ID).
 *
 * Outbound Email: SES SendEmail. Requires a verified sender (SES_FROM_EMAIL).
 *
 * Required env vars:
 *   SES_FROM_EMAIL              — verified SES sender (e.g. noreply@ecan.ai)
 *   SMS_ORIGINATION_IDENTITY    — phone number ARN, pool ID, or sender ID
 *   SMS_CONFIGURATION_SET       — (optional) for delivery event logging
 *
 * IAM permissions required on the Lambda role:
 *   ses:SendEmail
 *   sms-voice:SendTextMessage
 *
 * GraphQL contract:
 *   sendEmail(input: SendEmailInput!): MessagingResult
 *   sendSms(input: SendSmsInput!): MessagingResult
 *
 * MessagingResult shape: { success: Boolean, messageId: String, error: String }
 */

const { SESClient, SendEmailCommand } = require("@aws-sdk/client-ses");
const {
  PinpointSMSVoiceV2Client,
  SendTextMessageCommand,
} = require("@aws-sdk/client-pinpoint-sms-voice-v2");

const REGION = process.env.AWS_REGION || "us-east-1";

// Lazy-init clients so the module loads cleanly even if a deployment lacks one
// of the SDKs (e.g. SMS not configured yet).
let _sesClient = null;
function getSesClient() {
  if (!_sesClient) _sesClient = new SESClient({ region: REGION });
  return _sesClient;
}

let _smsClient = null;
function getSmsClient() {
  if (!_smsClient) _smsClient = new PinpointSMSVoiceV2Client({ region: REGION });
  return _smsClient;
}

// --- Validation helpers ---

const E164_REGEX = /^\+[1-9]\d{6,14}$/;
const EMAIL_REGEX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function _isValidE164(num) {
  return typeof num === "string" && E164_REGEX.test(num.trim());
}

function _isValidEmail(addr) {
  return typeof addr === "string" && EMAIL_REGEX.test(addr.trim());
}

// --- sendEmail ---

/**
 * Send an email via SES.
 * @param {Object} input  { to, subject, bodyText, bodyHtml?, replyTo? }
 * @param {String} owner  Caller identity (used for audit logging only).
 * @returns {Promise<{ success, messageId?, error? }>}
 */
async function sendEmail(input, owner) {
  const args = (input && input.input) || input || {};
  const { to, subject, bodyText, bodyHtml, replyTo } = args;

  const fromEmail = (process.env.SES_FROM_EMAIL || "").trim();
  if (!fromEmail) {
    return { success: false, error: "SES_FROM_EMAIL env var is not configured" };
  }
  if (!_isValidEmail(to)) {
    return { success: false, error: `Invalid recipient email: ${to}` };
  }
  if (!subject || typeof subject !== "string") {
    return { success: false, error: "subject is required" };
  }
  if (!bodyText && !bodyHtml) {
    return { success: false, error: "bodyText or bodyHtml is required" };
  }

  const body = {};
  if (bodyText) body.Text = { Charset: "UTF-8", Data: bodyText };
  if (bodyHtml) body.Html = { Charset: "UTF-8", Data: bodyHtml };

  try {
    const cmd = new SendEmailCommand({
      Source: fromEmail,
      Destination: { ToAddresses: [to.trim()] },
      Message: {
        Subject: { Charset: "UTF-8", Data: subject },
        Body: body,
      },
      ReplyToAddresses: replyTo ? [replyTo.trim()] : undefined,
    });
    const resp = await getSesClient().send(cmd);
    console.log(
      `[messagingService.sendEmail] Sent — owner=${owner}, to=${to}, messageId=${resp.MessageId}`,
    );
    return { success: true, messageId: resp.MessageId };
  } catch (e) {
    console.error(
      `[messagingService.sendEmail] Failed — owner=${owner}, to=${to}: ${e.message}`,
    );
    return { success: false, error: e.message };
  }
}

// --- sendSms ---

/**
 * Send an SMS via AWS End User Messaging SMS.
 * @param {Object} input  { phoneNumber, message }
 * @param {String} owner  Caller identity.
 * @returns {Promise<{ success, messageId?, error? }>}
 */
async function sendSms(input, owner) {
  const args = (input && input.input) || input || {};
  const { phoneNumber, message } = args;

  const origination = (process.env.SMS_ORIGINATION_IDENTITY || "").trim();
  if (!origination) {
    return {
      success: false,
      error: "SMS_ORIGINATION_IDENTITY env var is not configured",
    };
  }
  if (!_isValidE164(phoneNumber)) {
    return {
      success: false,
      error: `Invalid phoneNumber (must be E.164, e.g. +14155550100): ${phoneNumber}`,
    };
  }
  if (!message || typeof message !== "string" || !message.trim()) {
    return { success: false, error: "message is required" };
  }

  try {
    const cmd = new SendTextMessageCommand({
      DestinationPhoneNumber: phoneNumber.trim(),
      OriginationIdentity: origination,
      MessageBody: message,
      // Transactional = higher priority, lower throughput, more reliable for
      // the kind of 1:1 task notifications we expect from an agent system.
      MessageType: "TRANSACTIONAL",
      ConfigurationSetName: process.env.SMS_CONFIGURATION_SET || undefined,
    });
    const resp = await getSmsClient().send(cmd);
    console.log(
      `[messagingService.sendSms] Sent — owner=${owner}, to=${phoneNumber}, messageId=${resp.MessageId}`,
    );
    return { success: true, messageId: resp.MessageId };
  } catch (e) {
    console.error(
      `[messagingService.sendSms] Failed — owner=${owner}, to=${phoneNumber}: ${e.message}`,
    );
    return { success: false, error: e.message };
  }
}

module.exports = {
  sendEmail,
  sendSms,
};
