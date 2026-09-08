const http = require('http');
const fs = require('fs');
const path = require('path');

const fixturePath = path.join(__dirname, 'intervention-auth-fixture.html');
const semanticFixturePath = path.join(__dirname, 'semantic-grounding-fixture.html');
const dynamicDialogFixturePath = path.join(__dirname, 'dynamic-dialog-fixture.html');
const formConformanceFixturePath = path.join(__dirname, 'form-conformance-fixture.html');
const paginationConformanceFixturePath = path.join(__dirname, 'pagination-conformance-fixture.html');
const collectionConformanceFixturePath = path.join(__dirname, 'collection-conformance-fixture.html');
const server = http.createServer((request, response) => {
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
  response.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
  response.end('Not found');
});

server.listen(8765, '127.0.0.1');
