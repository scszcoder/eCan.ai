// 用户登录
import apiClient from "@/utils/request";

export const getImage = (params: any): Promise<any> => {
    // 返回的数据格式可以和服务端约定
    return apiClient.getFile('/api/v1/image', params).then(response => {
        return convertImageToBase64(response);
    })
}


export const cloudAnalyzeRandomImage = (params: any): Promise<any> => {
    // 返回的数据格式可以和服务端约定
    return apiClient.get('/api/v1/cloudAnalyzeRandomImage', params)
}
async function convertImageToBase64(imageData: any) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();

        reader.onload = (event) => {
            const base64String = event.target.result;
            resolve(base64String);
        };

        reader.onerror = (error) => {
            reject(error);
        };

        // 将Blob或ArrayBuffer转换为Base64
        if (imageData instanceof Blob) {
            reader.readAsDataURL(imageData);
        } else if (imageData instanceof ArrayBuffer) {
            const blob = new Blob([imageData], { type: 'image/*' });
            reader.readAsDataURL(blob);
        } else {
            reject(new Error('Unsupported data type'));
        }
    });
}
