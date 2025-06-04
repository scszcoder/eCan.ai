import sharp from 'sharp';
import path from 'path';
import { fileURLToPath } from 'url';
import fs from 'fs';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const svgPath = path.join(__dirname, '../src/modules/skill-editor/assets/icon-basic.svg');
const jpgPath = path.join(__dirname, '../src/modules/skill-editor/assets/icon-basic.jpg');

// Read SVG file
const svgBuffer = fs.readFileSync(svgPath);

// Convert SVG to JPG
sharp(svgBuffer)
  .jpeg({
    quality: 100,
    chromaSubsampling: '4:4:4'
  })
  .toFile(jpgPath)
  .then(() => {
    console.log('Successfully converted SVG to JPG');
  })
  .catch(err => {
    console.error('Error converting SVG to JPG:', err);
  }); 