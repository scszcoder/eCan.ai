'use strict';

const fs = require('node:fs');

function osRelease() {
  try {
    const values = Object.fromEntries(
      fs.readFileSync('/etc/os-release', 'utf8')
        .split('\n')
        .filter(Boolean)
        .map(line => line.split('=', 2))
        .map(([key, value]) => [key, String(value || '').replace(/^"|"$/g, '')]),
    );
    return {
      id: values.ID || null,
      idLike: values.ID_LIKE || null,
      versionId: values.VERSION_ID || null,
    };
  } catch {
    return { id: null, idLike: null, versionId: null };
  }
}

exports.main = async () => {
  const report = process.report.getReport().header;
  return {
    platform: process.platform,
    arch: process.arch,
    node: process.version,
    openssl: process.versions.openssl,
    glibc: report.glibcVersionRuntime || null,
    osName: report.osName || null,
    osRelease: report.osRelease || null,
    distribution: osRelease(),
  };
};