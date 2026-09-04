import React, { useEffect, useState } from 'react';
import { Button, Card, Col, Input, Modal, Row, Space, Tag, Typography, message } from 'antd';
import { CheckCircleFilled, ExclamationCircleFilled, MailOutlined, PhoneOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { useAccountStore } from '../../stores/accountStore';
import { ipcApi } from '../../services/ipc/api';
import { isWebPlatform } from '../../config/platform';

const { Title, Text } = Typography;

type Channel = 'email' | 'phone';

const RESEND_GAP_S = 60;

// Contact-verification handshake (CN, 2026-09-01): the server only commits
// accounts.email/phone after a 6-digit code round-trips (verify_send_code →
// verify_confirm on ecbAccountManager). This component never writes the
// contact value anywhere locally — the confirmed value comes back from the
// server in the verify_confirm response.
const ContactVerification: React.FC = () => {
    const { t } = useTranslation();
    const accountData = useAccountStore((s) => s.accountData);
    const setAccountData = useAccountStore((s) => s.setAccountData);
    const acct = (accountData as any)?.acctInfo || {};

    const [channel, setChannel] = useState<Channel | null>(null);
    const [step, setStep] = useState<'input' | 'code'>('input');
    const [target, setTarget] = useState('');
    const [code, setCode] = useState('');
    const [maskedTarget, setMaskedTarget] = useState('');
    const [sending, setSending] = useState(false);
    const [confirming, setConfirming] = useState(false);
    const [resendIn, setResendIn] = useState(0);

    useEffect(() => {
        if (resendIn <= 0) return;
        const timer = setInterval(() => setResendIn((s) => (s > 0 ? s - 1 : 0)), 1000);
        return () => clearInterval(timer);
    }, [resendIn > 0]);

    const errorText = (err: any): string => {
        const codeStr = String(err?.code || '');
        const attempts = err?.details?.remaining_attempts;
        switch (codeStr) {
            case 'retry_later':
                return t('account.verifyRetryLater', 'Please wait — a code can only be resent once every 60 seconds.');
            case 'hourly_limit':
                return t('account.verifyHourlyLimit', 'Too many codes requested — please try again in an hour.');
            case 'code_expired':
                return t('account.verifyCodeExpired', 'The code has expired — please request a new one.');
            case 'too_many_attempts':
                return t('account.verifyTooManyAttempts', 'Too many wrong attempts — please request a new code.');
            case 'invalid_code':
                return typeof attempts === 'number'
                    ? t('account.verifyInvalidCodeN', 'Incorrect code — {{n}} attempts remaining.', { n: attempts })
                    : t('account.verifyInvalidCode', 'Incorrect code.');
            case 'channel_not_configured':
                return t('account.verifyChannelUnavailable', 'This verification method is not available yet.');
            default:
                return err?.message || t('account.verifyFailed', 'Verification failed');
        }
    };

    const openModal = (ch: Channel) => {
        setChannel(ch);
        setStep('input');
        setTarget('');
        setCode('');
        setMaskedTarget('');
        setResendIn(0);
    };

    const handleSend = async () => {
        if (!channel || !target.trim()) return;
        setSending(true);
        try {
            const resp = await ipcApi.executeRequest('verify_send_code',
                { channel, target: target.trim() });
            if (resp?.success) {
                const data = resp.data as any;
                setMaskedTarget(data?.target || target.trim());
                setStep('code');
                setCode('');
                setResendIn(RESEND_GAP_S);
                message.success(t('account.verifyCodeSent',
                    'Verification code sent to {{target}} — valid for 10 minutes.',
                    { target: data?.target || target.trim() }));
            } else {
                message.error(errorText((resp as any)?.error));
            }
        } catch (e: any) {
            message.error(e?.message || String(e));
        } finally {
            setSending(false);
        }
    };

    const handleConfirm = async () => {
        if (!channel || code.trim().length !== 6) return;
        setConfirming(true);
        try {
            const resp = await ipcApi.executeRequest('verify_confirm',
                { channel, code: code.trim() });
            if (resp?.success) {
                const account = (resp.data as any)?.account;
                if (account && accountData) {
                    setAccountData({
                        ...(accountData as any),
                        acctInfo: { ...acct, ...account },
                    } as any);
                }
                message.success(t('account.verifySuccess', 'Verified — contact info updated.'));
                setChannel(null);
            } else {
                const err = (resp as any)?.error;
                message.error(errorText(err));
                const c = String(err?.code || '');
                if (c === 'code_expired' || c === 'too_many_attempts') {
                    setStep('input');
                    setCode('');
                }
            }
        } catch (e: any) {
            message.error(e?.message || String(e));
        } finally {
            setConfirming(false);
        }
    };

    const verifiedTag = (verified: boolean | undefined) => {
        if (verified === true) {
            return <Tag icon={<CheckCircleFilled />} color="success">
                {t('account.verifiedTag', 'Verified')}
            </Tag>;
        }
        if (verified === false) {
            return <Tag icon={<ExclamationCircleFilled />} color="warning">
                {t('account.unverifiedTag', 'Unverified')}
            </Tag>;
        }
        return null;
    };

    // Deadline nag: only when something is explicitly unverified.
    const unverified = acct.email_verified === false || acct.phone_verified === false;
    let daysLeft: number | null = null;
    if (unverified && acct.verify_deadline) {
        const ms = new Date(acct.verify_deadline).getTime() - Date.now();
        daysLeft = Math.max(0, Math.ceil(ms / 86400_000));
    }

    const canEdit = !isWebPlatform();

    const contactRow = (ch: Channel, value: string, verified: boolean | undefined) => (
        <Space size={12} wrap>
            {ch === 'email' ? <MailOutlined /> : <PhoneOutlined />}
            <Text type="secondary" style={{ minWidth: 48 }}>
                {ch === 'email' ? t('account.emailLabel', 'Email') : t('account.phoneLabel', 'Phone')}
            </Text>
            <Text strong>{value || t('account.notSet', 'Not set')}</Text>
            {verifiedTag(verified)}
            {canEdit && (
                <Button size="small" onClick={() => openModal(ch)}>
                    {value
                        ? t('account.changeAndVerify', 'Change & verify')
                        : t('account.addAndVerify', 'Add & verify')}
                </Button>
            )}
        </Space>
    );

    return (
        <Row gutter={[24, 24]} style={{ marginTop: 24 }}>
            <Col xs={24}>
                <Card>
                    <Space direction="vertical" size={12} style={{ width: '100%' }}>
                        <Title level={4} style={{ margin: 0 }}>
                            {t('account.contactInfo', 'Contact Info')}
                        </Title>
                        <Text type="secondary">
                            {t('account.contactDesc',
                                'Email and phone changes take effect after a 6-digit code is verified.')}
                        </Text>
                        {contactRow('email', acct.email || '', acct.email_verified)}
                        {contactRow('phone', acct.phone || '', acct.phone_verified)}
                        {daysLeft !== null && (
                            <Text type="danger">
                                {t('account.verifyDeadlineWarn',
                                    'Please complete verification within {{n}} days to keep your account active.',
                                    { n: daysLeft })}
                            </Text>
                        )}
                        {!canEdit && (
                            <Text type="secondary">
                                {t('account.verifyDesktopOnly',
                                    'Contact changes are currently available in the desktop app.')}
                            </Text>
                        )}
                    </Space>
                </Card>
            </Col>

            <Modal
                open={channel !== null}
                title={channel === 'phone'
                    ? t('account.verifyPhoneTitle', 'Verify phone number')
                    : t('account.verifyEmailTitle', 'Verify email address')}
                onCancel={() => setChannel(null)}
                footer={null}
                destroyOnHidden
            >
                <Space direction="vertical" size={12} style={{ width: '100%' }}>
                    {step === 'input' ? (
                        <>
                            <Input
                                autoFocus
                                prefix={channel === 'phone' ? <PhoneOutlined /> : <MailOutlined />}
                                placeholder={channel === 'phone'
                                    ? t('account.phonePlaceholder', 'Phone number (e.g. 13812345678)')
                                    : t('account.emailPlaceholder', 'Email address')}
                                value={target}
                                onChange={(e) => setTarget(e.target.value)}
                                onPressEnter={handleSend}
                            />
                            <Button type="primary" block loading={sending}
                                disabled={!target.trim() || resendIn > 0}
                                onClick={handleSend}>
                                {resendIn > 0
                                    ? t('account.resendIn', 'Resend in {{s}}s', { s: resendIn })
                                    : t('account.sendCode', 'Send verification code')}
                            </Button>
                        </>
                    ) : (
                        <>
                            <Text>
                                {t('account.codeSentTo', 'Code sent to {{target}} — valid for 10 minutes.',
                                    { target: maskedTarget })}
                            </Text>
                            <Input
                                autoFocus
                                maxLength={6}
                                placeholder={t('account.codePlaceholder', '6-digit code')}
                                value={code}
                                style={{ fontVariantNumeric: 'tabular-nums', letterSpacing: 4 }}
                                onChange={(e) => setCode(e.target.value.replace(/\D/g, ''))}
                                onPressEnter={handleConfirm}
                            />
                            <Button type="primary" block loading={confirming}
                                disabled={code.trim().length !== 6}
                                onClick={handleConfirm}>
                                {t('account.confirmCode', 'Verify')}
                            </Button>
                            <Button type="link" block loading={sending}
                                disabled={resendIn > 0}
                                onClick={handleSend}>
                                {resendIn > 0
                                    ? t('account.resendIn', 'Resend in {{s}}s', { s: resendIn })
                                    : t('account.resendCode', 'Resend code')}
                            </Button>
                        </>
                    )}
                </Space>
            </Modal>
        </Row>
    );
};

export default ContactVerification;
