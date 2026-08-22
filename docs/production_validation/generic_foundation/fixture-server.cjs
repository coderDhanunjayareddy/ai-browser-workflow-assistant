const http = require('http');
const fs = require('fs');
const path = require('path');

const fixturePath = path.join(__dirname, 'intervention-auth-fixture.html');
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
  response.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
  response.end('Not found');
});

server.listen(8765, '127.0.0.1');
