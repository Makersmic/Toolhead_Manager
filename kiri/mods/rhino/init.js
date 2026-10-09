// Kiri:Moto server-side hook for the Rhino bridge: adds rhino.js to the Kiri:Moto page.
// Copied into Kiri:Moto's mods/ folder by dev/kiri_build.sh.
module.exports = function(server) {
    server.inject("kiri", "rhino.js");
};
