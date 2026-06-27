import React, { useEffect, useState } from 'react';
import { Empty, Spin, Typography, Input, Button, Space, App } from 'antd';
import { ClockCircleOutlined, PlusOutlined, HistoryOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import styled from '@emotion/styled';
import { get_ipc_api } from '@/services/ipc_api';
import type { Skill, SkillChangelogEntry } from '@/types/domain/skill';

const { Text } = Typography;

const Card = styled.div`
    background: var(--bg-secondary);
    border: 1px solid rgba(255, 255, 255, 0.06);
    border-radius: 14px;
    padding: 16px;
    margin-bottom: 16px;
`;

const Timeline = styled.div`
    position: relative;
    padding-left: 22px;

    &::before {
        content: '';
        position: absolute;
        top: 6px;
        bottom: 6px;
        left: 8px;
        width: 2px;
        background: linear-gradient(180deg, rgba(24, 144, 255, 0.5), rgba(255, 255, 255, 0.06));
        border-radius: 2px;
    }
`;

const Item = styled.div`
    position: relative;
    padding: 6px 0 14px 0;

    &::before {
        content: '';
        position: absolute;
        top: 10px;
        left: -19px;
        width: 12px;
        height: 12px;
        border-radius: 50%;
        background: #1890ff;
        box-shadow: 0 0 0 3px rgba(24, 144, 255, 0.18);
    }

    &:last-child {
        padding-bottom: 0;
    }
`;

const VersionRow = styled.div`
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 2px;
`;

const VersionTag = styled.span`
    background: rgba(24, 144, 255, 0.15);
    color: #69c0ff;
    border: 1px solid rgba(24, 144, 255, 0.35);
    font-family: monospace;
    font-size: 11px;
    font-weight: 600;
    padding: 1px 8px;
    border-radius: 6px;
`;

const Notes = styled.div`
    font-size: 13px;
    color: rgba(255, 255, 255, 0.78);
    line-height: 1.55;
`;

const DateText = styled.div`
    font-size: 11px;
    color: rgba(255, 255, 255, 0.4);
    margin-bottom: 4px;
`;

interface Props {
    skill: Skill;
    canEdit?: boolean;
}

const SkillChangelog: React.FC<Props> = ({ skill, canEdit }) => {
    const { t } = useTranslation();
    const { message } = App.useApp();
    const [entries, setEntries] = useState<SkillChangelogEntry[]>([]);
    const [loading, setLoading] = useState(false);
    const [draftOpen, setDraftOpen] = useState(false);
    const [draftVersion, setDraftVersion] = useState('');
    const [draftNotes, setDraftNotes] = useState('');
    const [submitting, setSubmitting] = useState(false);

    const loadEntries = () => {
        if (!skill?.id) return;
        setLoading(true);
        const api = get_ipc_api();
        api.getSkillChangelog(String(skill.id))
            .then((resp: any) => {
                if (resp?.success) {
                    const data = (resp.data as any)?.data ?? resp.data ?? [];
                    setEntries(Array.isArray(data) ? data : []);
                } else {
                    setEntries(Array.isArray((skill as any).changelog) ? (skill as any).changelog : []);
                }
            })
            .catch(() => {
                setEntries(Array.isArray((skill as any).changelog) ? (skill as any).changelog : []);
            })
            .finally(() => setLoading(false));
    };

    useEffect(() => {
        loadEntries();
    }, [skill?.id]);

    const submit = async () => {
        if (!draftVersion.trim()) {
            message.warning(t('pages.skills.changelog.versionRequired', 'Please enter a version'));
            return;
        }
        setSubmitting(true);
        try {
            const api = get_ipc_api();
            const resp = await api.appendSkillChangelog(String(skill.id), draftVersion.trim(), draftNotes.trim());
            if (resp?.success) {
                message.success(t('pages.skills.changelog.appended', 'Changelog entry added'));
                setDraftOpen(false);
                setDraftVersion('');
                setDraftNotes('');
                loadEntries();
            } else {
                message.error(t('pages.skills.changelog.appendFailed', 'Failed to add entry'));
            }
        } catch {
            message.error(t('pages.skills.changelog.appendFailed', 'Failed to add entry'));
        } finally {
            setSubmitting(false);
        }
    };

    return (
        <Card>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
                <Text style={{ fontSize: 11, color: 'rgba(255,255,255,0.5)', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                    <HistoryOutlined style={{ marginRight: 4 }} />
                    {t('pages.skills.changelog.title', 'Changelog')}
                </Text>
                {canEdit && !draftOpen && (
                    <Button size="small" icon={<PlusOutlined />} onClick={() => setDraftOpen(true)}>
                        {t('pages.skills.changelog.add', 'Add entry')}
                    </Button>
                )}
            </div>

            {canEdit && draftOpen && (
                <div style={{ marginBottom: 12, padding: 12, background: 'rgba(24,144,255,0.06)', border: '1px solid rgba(24,144,255,0.2)', borderRadius: 10 }}>
                    <Space direction="vertical" style={{ width: '100%' }} size={8}>
                        <Input
                            placeholder={t('pages.skills.changelog.versionPlaceholder', 'e.g., 1.2.0')}
                            value={draftVersion}
                            onChange={(e) => setDraftVersion(e.target.value)}
                        />
                        <Input.TextArea
                            rows={2}
                            placeholder={t('pages.skills.changelog.notesPlaceholder', 'What changed in this version?')}
                            value={draftNotes}
                            onChange={(e) => setDraftNotes(e.target.value)}
                        />
                        <Space>
                            <Button type="primary" size="small" loading={submitting} onClick={submit}>
                                {t('common.submit', 'Submit')}
                            </Button>
                            <Button size="small" onClick={() => { setDraftOpen(false); setDraftVersion(''); setDraftNotes(''); }}>
                                {t('common.cancel', 'Cancel')}
                            </Button>
                        </Space>
                    </Space>
                </div>
            )}

            {loading ? (
                <div style={{ textAlign: 'center', padding: 20 }}>
                    <Spin size="small" />
                </div>
            ) : entries.length === 0 ? (
                <Empty
                    image={Empty.PRESENTED_IMAGE_SIMPLE}
                    description={t('pages.skills.changelog.empty', 'No changelog entries yet.')}
                />
            ) : (
                <Timeline>
                    {entries.map((entry, idx) => (
                        <Item key={`${entry.version}-${idx}`}>
                            <VersionRow>
                                <VersionTag>v{entry.version}</VersionTag>
                                {entry.date && (
                                    <DateText>
                                        <ClockCircleOutlined /> {new Date(entry.date).toLocaleDateString()}
                                    </DateText>
                                )}
                            </VersionRow>
                            {entry.notes && <Notes>{entry.notes}</Notes>}
                        </Item>
                    ))}
                </Timeline>
            )}
        </Card>
    );
};

export default SkillChangelog;
