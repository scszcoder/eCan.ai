import { useState, useRef, ChangeEvent } from 'react';
import { Attachment } from '../types/chat';

export const useAttachmentHandler = () => {
    const [attachments, setAttachments] = useState<Attachment[]>([]);
    const [isRecording, setIsRecording] = useState(false);
    const [mediaRecorder, setMediaRecorder] = useState<MediaRecorder | null>(null);
    const fileInputRef = useRef<HTMLInputElement>(null);

    const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
        const files = e.target.files;
        if (!files) return;

        const newAttachments: Attachment[] = Array.from(files).map(file => ({
            id: Date.now().toString(),
            type: file.type.startsWith('image/') ? 'image' : 'file',
            name: file.name,
            size: file.size,
            url: URL.createObjectURL(file)
        }));

        setAttachments(prev => [...prev, ...newAttachments]);
    };

    const addAttachment = (attachment: Attachment) => {
        setAttachments(prev => [...prev, attachment]);
    };

    const removeAttachment = (id: string) => {
        setAttachments(prev => prev.filter(attachment => attachment.id !== id));
    };

    const clearAttachments = () => {
        setAttachments([]);
    };

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            const recorder = new MediaRecorder(stream);
            const audioChunks: Blob[] = [];

            recorder.ondataavailable = (event) => {
                if (event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            };

            recorder.onstop = () => {
                const audioBlob = new Blob(audioChunks, { type: 'audio/wav' });
                const audioFile = new File([audioBlob], `recording-${Date.now()}.wav`, {
                    type: 'audio/wav',
                });

                setAttachments(prev => [...prev, {
                    id: Date.now().toString(),
                    name: `Voice Message ${new Date().toLocaleTimeString()}`,
                    type: 'audio/wav',
                    size: audioBlob.size,
                    file: audioFile,
                    url: URL.createObjectURL(audioBlob)
                }]);

                stream.getTracks().forEach(track => track.stop());
            };

            recorder.start();
            setMediaRecorder(recorder);
            setIsRecording(true);
        } catch (error) {
            console.error('Error starting recording:', error);
        }
    };

    const stopRecording = () => {
        if (mediaRecorder && isRecording) {
            mediaRecorder.stop();
            setIsRecording(false);
            setMediaRecorder(null);
        }
    };

    return {
        attachments,
        isRecording,
        fileInputRef,
        handleFileChange,
        addAttachment,
        removeAttachment,
        clearAttachments,
        startRecording,
        stopRecording
    };
}; 