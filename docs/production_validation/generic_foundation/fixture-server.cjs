const http = require('http');
const fs = require('fs');
const path = require('path');

const fixturePath = path.join(__dirname, 'intervention-auth-fixture.html');
const semanticFixturePath = path.join(__dirname, 'semantic-grounding-fixture.html');
const dynamicDialogFixturePath = path.join(__dirname, 'dynamic-dialog-fixture.html');
const formConformanceFixturePath = path.join(__dirname, 'form-conformance-fixture.html');
const paginationConformanceFixturePath = path.join(__dirname, 'pagination-conformance-fixture.html');
const collectionConformanceFixturePath = path.join(__dirname, 'collection-conformance-fixture.html');
const frameConformanceFixturePath = path.join(__dirname, 'frame-conformance-fixture.html');
const frameConformanceChildPath = path.join(__dirname, 'frame-conformance-child.html');
const downloadConformanceFixturePath = path.join(__dirname, 'download-conformance-fixture.html');
const contentInsertionConformanceFixturePath = path.join(__dirname, 'content-insertion-conformance-fixture.html');
const promptInjectionFixturePath = path.join(__dirname, 'prompt-injection-conformance-fixture.html');
const accountAmbiguityFixturePath = path.join(__dirname, 'account-ambiguity-conformance-fixture.html');
const crossOriginParentFixturePath = path.join(__dirname, 'cross-origin-parent-fixture.html');
const crossOriginChildFixturePath = path.join(__dirname, 'cross-origin-child-fixture.html');
const syntheticDownloadPath = path.join(__dirname, 'synthetic-download.txt');
const server = http.createServer((request, response) => {
  console.log(`${new Date().toISOString()} ${request.method} ${request.url}`);
  if (request.url === '/health') {
    response.writeHead(200, { 'content-type': 'application/json', 'cache-control': 'no-store' });
    response.end(JSON.stringify({ status: 'ok', fixture: 'generic-human-intervention' }));
    return;
  }
  if (request.url?.startsWith('/intervention-auth-fixture.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(fixturePath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/semantic-grounding-fixture.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(semanticFixturePath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/dynamic-dialog-fixture.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(dynamicDialogFixturePath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/form-conformance-fixture.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(formConformanceFixturePath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/pagination-conformance-fixture.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(paginationConformanceFixturePath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/collection-conformance-fixture.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(collectionConformanceFixturePath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/frame-conformance-fixture.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(frameConformanceFixturePath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/frame-conformance-child.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(frameConformanceChildPath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/download-conformance-fixture.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(downloadConformanceFixturePath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/content-insertion-conformance-fixture.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(contentInsertionConformanceFixturePath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/prompt-injection-conformance-fixture.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(promptInjectionFixturePath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/account-ambiguity-conformance-fixture.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(accountAmbiguityFixturePath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/cross-origin-parent-fixture.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(crossOriginParentFixturePath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/cross-origin-child-fixture.html')) {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    fs.createReadStream(crossOriginChildFixturePath).pipe(response);
    return;
  }
  if (request.url?.startsWith('/synthetic-download.txt')) {
    const size = fs.statSync(syntheticDownloadPath).size;
    response.writeHead(200, {
      'content-type': 'text/plain; charset=utf-8',
      'content-length': size,
      'content-disposition': 'attachment; filename="synthetic-download.txt"',
      'cache-control': 'no-store',
    });
    fs.createReadStream(syntheticDownloadPath).pipe(response);
    return;
  }
  response.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
  response.end('Not found');
});

const requestedPort = Number(process.argv[2] || 8765);
if (!Number.isInteger(requestedPort) || requestedPort < 1024 || requestedPort > 65535) {
  throw new Error(`Invalid fixture port: ${process.argv[2]}`);
}
server.listen(requestedPort, '127.0.0.1');
