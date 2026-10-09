// PROTOTYPE (developer use). Prints the node_modules folders the Kiri:Moto server needs: the
// packages in kiri/SERVER_PACKAGES (what app.js, the app server and the bundled mods require) and
// everything they depend on, resolved the way Node does. Optional dependencies are skipped (they are
// native helpers). Folders nested inside a package come along with it.
const fs = require('fs'), path = require('path');
const root = path.resolve(process.argv[2]);
const nm = path.join(root, 'node_modules');
const wanted = fs.readFileSync(path.join(__dirname, '..', 'kiri', 'SERVER_PACKAGES'), 'utf8').split('\n').map(s => s.trim()).filter(Boolean);
const top = new Set();
const seen = new Set();
function resolve(name, fromDir) {
    let dir = fromDir;
    while (dir.startsWith(nm)) {
        const p = path.join(dir, 'node_modules', name);
        if (fs.existsSync(path.join(p, 'package.json'))) return p;
        dir = path.dirname(dir);
    }
    const p = path.join(nm, name);
    return fs.existsSync(path.join(p, 'package.json')) ? p : null;
}
function walk(dir) {
    if (seen.has(dir)) return;
    seen.add(dir);
    const rel = path.relative(nm, dir);
    if (!rel.includes('node_modules')) top.add(rel);
    const pkg = JSON.parse(fs.readFileSync(path.join(dir, 'package.json'), 'utf8'));
    for (const d of Object.keys(pkg.dependencies || {})) {
        const r = resolve(d, dir);
        if (!r) { console.error(`missing: ${d} (needed by ${rel})`); process.exitCode = 1; continue; }
        walk(r);
    }
}
for (const w of wanted) {
    const r = resolve(w, nm);
    if (!r) { console.error(`missing: ${w}`); process.exitCode = 1; continue; }
    walk(r);
}
console.log([...top].sort().join('\n'));
