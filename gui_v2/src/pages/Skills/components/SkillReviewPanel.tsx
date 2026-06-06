/**
 * SkillReviewPanel: Display and submit skill reviews/ratings.
 * Integrated as a tab in SkillDetails.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { Button, Space, Input, Typography, Avatar, message, Spin } from 'antd';
import { StarFilled, StarOutlined, DeleteOutlined, EditOutlined, UserOutlined } from '@ant-design/icons';
import { useTranslation } from 'react-i18next';
import { get_ipc_api } from '@/services/ipc_api';
import { logger } from '@/utils/logger';
import styled from '@emotion/styled';

const { Text } = Typography;
const { TextArea } = Input;

interface Review {
    id: string;
    skill_id: string;
    reviewer_id: string;
    reviewer_name?: string;
    rating: number;
    review_text?: string;
    helpful: number;
    created_at: string;
    updated_at?: string;
}

interface RatingStats {
    total: number;
    avgRating: number;
    totalHelpful: number;
    distribution?: Record<number, number>;
}

interface SkillReviewPanelProps {
    skillId: string;
    username: string;
    owner?: string;
}

const PanelContainer = styled.div`
    padding: 4px 0;
`;

const SummaryCard = styled.div`
    display: flex;
    align-items: stretch;
    gap: 0;
    background: var(--bg-secondary);
    border-radius: 14px;
    border: 1px solid rgba(255, 255, 255, 0.06);
    overflow: hidden;
    margin-bottom: 16px;
`;

const SummaryScore = styled.div`
    min-width: 120px;
    padding: 20px 16px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    background: linear-gradient(135deg, rgba(250, 173, 20, 0.08), rgba(250, 173, 20, 0.03));
    border-right: 1px solid rgba(255, 255, 255, 0.05);
`;

const SummaryDist = styled.div`
    flex: 1;
    padding: 16px 20px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 5px;
`;

const RatingRow = styled.div`
    display: flex;
    align-items: center;
    gap: 8px;
`;

const RatingBarWrap = styled.div`
    flex: 1;
    height: 5px;
    background: rgba(255, 255, 255, 0.06);
    border-radius: 3px;
    overflow: hidden;
`;

const ReviewCard = styled.div`
    padding: 14px 16px;
    background: var(--bg-secondary);
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.05);
    margin-bottom: 8px;
    transition: border-color 0.15s;

    &:hover {
        border-color: rgba(255, 255, 255, 0.1);
    }
`;

const ReviewForm = styled.div`
    padding: 16px;
    background: linear-gradient(135deg, rgba(24, 144, 255, 0.06), rgba(24, 144, 255, 0.02));
    border-radius: 12px;
    border: 1px solid rgba(24, 144, 255, 0.15);
    margin-bottom: 16px;
`;

const SectionTitle = styled.div`
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    color: rgba(255, 255, 255, 0.4);
    margin-bottom: 10px;
`;

const StarRatingInput: React.FC<{ value: number; onChange: (v: number) => void }> = ({ value, onChange }) => (
    <Space size={3}>
        {[1, 2, 3, 4, 5].map((star) => (
            <span
                key={star}
                onClick={() => onChange(star)}
                onMouseEnter={(e) => {
                    if (star <= value) (e.currentTarget as HTMLElement).style.transform = 'scale(1.2)';
                }}
                onMouseLeave={(e) => {
                    (e.currentTarget as HTMLElement).style.transform = 'scale(1)';
                }}
                style={{
                    cursor: 'pointer',
                    fontSize: 26,
                    color: star <= value ? '#faad14' : 'rgba(255,255,255,0.15)',
                    transition: 'color 0.12s, transform 0.1s',
                    display: 'inline-block',
                }}
            >
                {star <= value ? <StarFilled /> : <StarOutlined />}
            </span>
        ))}
    </Space>
);

const StarRatingDisplay: React.FC<{ rating: number; size?: number }> = ({ rating, size = 14 }) => (
    <Space size={1}>
        {[1, 2, 3, 4, 5].map((star) => (
            <span key={star} style={{
                color: star <= rating ? '#faad14' : 'rgba(255,255,255,0.12)',
                fontSize: size,
                lineHeight: 1,
            }}>
                ★
            </span>
        ))}
    </Space>
);

const ReviewerAvatar: React.FC<{ name: string; size?: number; color?: string }> = ({
    name, size = 32, color = '#8b5cf6'
}) => (
    <Avatar
        size={size}
        style={{
            background: `linear-gradient(135deg, ${color}, ${color}88)`,
            fontSize: size * 0.4,
            fontWeight: 700,
            flexShrink: 0,
        }}
        icon={<UserOutlined />}
    >
        {name?.[0]?.toUpperCase()}
    </Avatar>
);

export const SkillReviewPanel: React.FC<SkillReviewPanelProps> = ({
    skillId,
    username,
    owner,
}) => {
    const { t } = useTranslation();
    const [reviews, setReviews] = useState<Review[]>([]);
    const [stats, setStats] = useState<RatingStats>({ total: 0, avgRating: 0, totalHelpful: 0 });
    const [myReview, setMyReview] = useState<Review | null>(null);
    const [loading, setLoading] = useState(false);
    const [submitting, setSubmitting] = useState(false);
    const [rating, setRating] = useState(0);
    const [reviewText, setReviewText] = useState('');
    const [showForm, setShowForm] = useState(false);

    const isOwnSkill = owner && owner.toLowerCase() === username.toLowerCase();

    const fetchReviews = useCallback(async () => {
        if (!skillId) return;
        setLoading(true);
        try {
            const api = get_ipc_api();
            const resp = await api?.getSkillReviews(skillId) as any;
            if (resp?.success && resp?.data) {
                const data = resp.data;
                const reviewList = Array.isArray(data.reviews) ? data.reviews : [];
                setReviews(reviewList);
                setStats(data.stats || { total: 0, avgRating: 0, totalHelpful: 0 });
                const mine = reviewList.find(
                    (r: Review) => r.reviewer_id?.toLowerCase() === username.toLowerCase()
                );
                setMyReview(mine || null);
                if (mine) {
                    setRating(mine.rating);
                    setReviewText(mine.review_text || '');
                }
            }
        } catch (e) {
            logger.error('[SkillReviewPanel] fetch error:', e);
        } finally {
            setLoading(false);
        }
    }, [skillId, username]);

    useEffect(() => { fetchReviews(); }, [fetchReviews]);

    const submit = async () => {
        if (!rating) {
            message.warning(t('pages.skills.reviews.ratingRequired', 'Please select a rating'));
            return;
        }
        setSubmitting(true);
        try {
            const api = get_ipc_api();
            const resp = await api?.upsertSkillReview(skillId, username, rating, reviewText) as any;
            if (resp?.success) {
                message.success(t('pages.skills.reviews.submitted', 'Review submitted'));
                setShowForm(false);
                await fetchReviews();
            } else {
                message.error(resp?.error?.message || t('pages.skills.reviews.submitFailed', 'Failed to submit review'));
            }
        } catch (e) {
            logger.error('[SkillReviewPanel] submit error:', e);
            message.error(t('pages.skills.reviews.submitFailed', 'Failed to submit review'));
        } finally {
            setSubmitting(false);
        }
    };

    const deleteMyReview = async () => {
        if (!myReview) return;
        try {
            const api = get_ipc_api();
            const resp = await api?.deleteSkillReview(myReview.id, username) as any;
            if (resp?.success) {
                message.success(t('pages.skills.reviews.deleted', 'Review deleted'));
                setRating(0);
                setReviewText('');
                setMyReview(null);
                await fetchReviews();
            } else {
                message.error(t('pages.skills.reviews.deleteFailed', 'Failed to delete review'));
            }
        } catch (e) {
            logger.error('[SkillReviewPanel] delete error:', e);
            message.error(t('pages.skills.reviews.deleteFailed', 'Failed to delete review'));
        }
    };

    const dist = stats.distribution || { 1: 0, 2: 0, 3: 0, 4: 0, 5: 0 };

    return (
        <PanelContainer>
            {loading ? (
                <div style={{ textAlign: 'center', padding: 40 }}>
                    <Spin />
                </div>
            ) : (
                <>
                    {/* Summary Card */}
                    <SummaryCard>
                        <SummaryScore>
                            <div style={{
                                fontSize: 40,
                                fontWeight: 800,
                                color: stats.avgRating > 0 ? '#faad14' : 'rgba(255,255,255,0.3)',
                                lineHeight: 1,
                                letterSpacing: -1,
                            }}>
                                {stats.avgRating > 0 ? stats.avgRating.toFixed(1) : '—'}
                            </div>
                            <StarRatingDisplay rating={Math.round(stats.avgRating)} size={16} />
                            <Text style={{ fontSize: 11, color: 'rgba(255,255,255,0.4)', marginTop: 4 }}>
                                {t('pages.skills.reviews.count', { count: stats.total })}
                            </Text>
                        </SummaryScore>
                        <SummaryDist>
                            {[5, 4, 3, 2, 1].map((star) => {
                                const count = dist?.[star] || reviews.filter(r => r.rating === star).length;
                                const pct = stats.total > 0 ? (count / stats.total * 100) : 0;
                                return (
                                    <RatingRow key={star}>
                                        <Text style={{ fontSize: 12, color: 'rgba(255,255,255,0.45)', width: 12 }}>{star}</Text>
                                        <span style={{ color: '#faad14', fontSize: 11 }}>★</span>
                                        <RatingBarWrap>
                                            <div style={{
                                                width: `${pct}%`,
                                                height: '100%',
                                                background: 'linear-gradient(90deg, #faad14aa, #faad14)',
                                                borderRadius: 3,
                                                transition: 'width 0.4s',
                                                minWidth: pct > 0 ? 4 : 0,
                                            }} />
                                        </RatingBarWrap>
                                        <Text style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)', width: 20, textAlign: 'right' }}>{count}</Text>
                                    </RatingRow>
                                );
                            })}
                        </SummaryDist>
                    </SummaryCard>

                    {/* Write / Edit Review */}
                    {!isOwnSkill && (
                        <div>
                            {!showForm && !myReview && (
                                <Button
                                    type="default"
                                    onClick={() => setShowForm(true)}
                                    style={{
                                        borderRadius: 10,
                                        height: 36,
                                        fontWeight: 500,
                                        border: '1px solid rgba(255,255,255,0.1)',
                                        background: 'rgba(255,255,255,0.04)',
                                        color: 'rgba(255,255,255,0.75)',
                                        marginBottom: 16,
                                    }}
                                >
                                    <StarOutlined style={{ color: '#faad14', marginRight: 6 }} />
                                    {t('pages.skills.reviews.write', 'Write a Review')}
                                </Button>
                            )}
                            {showForm && (
                                <ReviewForm>
                                    <div style={{ marginBottom: 12 }}>
                                        <Text style={{ marginRight: 12, color: 'rgba(255,255,255,0.6)', fontSize: 13 }}>
                                            {t('pages.skills.reviews.yourRating', 'Your Rating')}
                                        </Text>
                                        <StarRatingInput value={rating} onChange={setRating} />
                                    </div>
                                    <TextArea
                                        value={reviewText}
                                        onChange={(e) => setReviewText(e.target.value)}
                                        placeholder={t('pages.skills.reviews.placeholder', 'Share your experience with this skill... (optional)')}
                                        rows={3}
                                        style={{
                                            marginBottom: 12,
                                            borderRadius: 10,
                                            background: 'rgba(0,0,0,0.2)',
                                            border: '1px solid rgba(255,255,255,0.08)',
                                            color: 'rgba(255,255,255,0.85)',
                                        }}
                                    />
                                    <Space>
                                        <Button
                                            type="primary"
                                            loading={submitting}
                                            onClick={submit}
                                            style={{ borderRadius: 8, height: 34 }}
                                        >
                                            {t('pages.skills.reviews.submit', 'Submit Review')}
                                        </Button>
                                        <Button
                                            onClick={() => {
                                                setShowForm(false);
                                                setRating(myReview?.rating || 0);
                                                setReviewText(myReview?.review_text || '');
                                            }}
                                            style={{ borderRadius: 8, height: 34 }}
                                        >
                                            {t('common.cancel', 'Cancel')}
                                        </Button>
                                    </Space>
                                </ReviewForm>
                            )}
                        </div>
                    )}

                    {/* My existing review */}
                    {myReview && (
                        <ReviewCard style={{
                            background: 'linear-gradient(135deg, rgba(24,144,255,0.06), rgba(24,144,255,0.02))',
                            border: '1px solid rgba(24,144,255,0.15)',
                        }}>
                            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 10 }}>
                                <Space size={10}>
                                    <ReviewerAvatar name={username} size={32} color="#1890ff" />
                                    <div>
                                        <Text style={{ fontSize: 13, fontWeight: 600, color: 'white', display: 'block' }}>
                                            {username}
                                        </Text>
                                        <StarRatingDisplay rating={myReview.rating} size={12} />
                                    </div>
                                </Space>
                                <Space size={4}>
                                    {!showForm && (
                                        <Button
                                            size="small"
                                            icon={<EditOutlined />}
                                            onClick={() => setShowForm(true)}
                                            style={{ borderRadius: 6, fontSize: 12 }}
                                        >
                                            {t('common.edit', 'Edit')}
                                        </Button>
                                    )}
                                    <Button
                                        size="small"
                                        danger
                                        icon={<DeleteOutlined />}
                                        onClick={deleteMyReview}
                                        style={{ borderRadius: 6, fontSize: 12 }}
                                    />
                                </Space>
                            </div>
                            {myReview.review_text && (
                                <Text style={{ fontSize: 13, color: 'rgba(255,255,255,0.75)', lineHeight: 1.6 }}>
                                    {myReview.review_text}
                                </Text>
                            )}
                            {showForm && (
                                <div style={{ marginTop: 12 }}>
                                    <Text style={{ color: 'rgba(255,255,255,0.5)', fontSize: 12, display: 'block', marginBottom: 8 }}>
                                        {t('pages.skills.reviews.yourRating', 'Your Rating')}
                                    </Text>
                                    <StarRatingInput value={rating} onChange={setRating} />
                                    <TextArea
                                        value={reviewText}
                                        onChange={(e) => setReviewText(e.target.value)}
                                        rows={2}
                                        style={{
                                            marginTop: 10,
                                            marginBottom: 10,
                                            borderRadius: 8,
                                            background: 'rgba(0,0,0,0.2)',
                                            border: '1px solid rgba(255,255,255,0.08)',
                                            color: 'rgba(255,255,255,0.85)',
                                        }}
                                    />
                                    <Space>
                                        <Button type="primary" loading={submitting} onClick={submit} style={{ borderRadius: 8, height: 32 }}>
                                            {t('pages.skills.reviews.update', 'Update')}
                                        </Button>
                                        <Button onClick={() => setShowForm(false)} style={{ borderRadius: 8, height: 32 }}>
                                            {t('common.cancel', 'Cancel')}
                                        </Button>
                                    </Space>
                                </div>
                            )}
                        </ReviewCard>
                    )}

                    {/* Other reviews */}
                    {(() => {
                        const otherReviews = reviews.filter(
                            r => r.reviewer_id?.toLowerCase() !== username.toLowerCase()
                        );
                        if (otherReviews.length === 0) return null;
                        return (
                            <>
                                <SectionTitle>
                                    {t('pages.skills.reviews.allReviews', 'All Reviews')} ({otherReviews.length})
                                </SectionTitle>
                                {otherReviews.map((review) => (
                                    <ReviewCard key={review.id}>
                                        <Space size={10} style={{ marginBottom: 6 }}>
                                            <ReviewerAvatar name={review.reviewer_name || review.reviewer_id} size={28} color="#8b5cf6" />
                                            <div>
                                                <Text style={{ fontSize: 13, fontWeight: 500, color: 'white', display: 'block' }}>
                                                    {review.reviewer_name || review.reviewer_id}
                                                </Text>
                                                <Space size={4}>
                                                    <StarRatingDisplay rating={review.rating} size={12} />
                                                    <Text style={{ fontSize: 11, color: 'rgba(255,255,255,0.3)' }}>
                                                        {new Date(review.created_at).toLocaleDateString()}
                                                    </Text>
                                                </Space>
                                            </div>
                                        </Space>
                                        {review.review_text && (
                                            <Text style={{ fontSize: 13, color: 'rgba(255,255,255,0.7)', lineHeight: 1.6, display: 'block', marginLeft: 38 }}>
                                                {review.review_text}
                                            </Text>
                                        )}
                                    </ReviewCard>
                                ))}
                            </>
                        );
                    })()}

                    {reviews.length === 0 && !myReview && (
                        <div style={{
                            textAlign: 'center',
                            padding: '28px 0',
                            color: 'rgba(255,255,255,0.3)',
                            fontSize: 13,
                        }}>
                            <StarOutlined style={{ fontSize: 24, marginBottom: 8, display: 'block', opacity: 0.3 }} />
                            {t('pages.skills.reviews.noReviews', 'No reviews yet. Be the first to review!')}
                        </div>
                    )}
                </>
            )}
        </PanelContainer>
    );
};
