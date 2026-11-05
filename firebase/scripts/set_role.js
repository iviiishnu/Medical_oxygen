#!/usr/bin/env node
'use strict';
/**
 * Give a Firebase Auth user a role (custom claim) and, for staff, create their staff doc.
 *
 *   node scripts/set_role.js --email nurse1@hospital.org --role staff --name "Nurse 1" --order 1
 *   node scripts/set_role.js --email tablet01@hospital.org --role device --device tab-main-o2-01
 *   node scripts/set_role.js --email you@x.com --role admin
 * The user must sign out and in again (or wait ~1 h) for the claim to apply.
 */
const path = require('path');
const fnDir = path.join(__dirname, '..', 'functions');
const { initializeApp } = require(require.resolve('firebase-admin/app', { paths: [fnDir] }));
const { getAuth } = require(require.resolve('firebase-admin/auth', { paths: [fnDir] }));
const { getFirestore } = require(require.resolve('firebase-admin/firestore', { paths: [fnDir] }));

function arg(n, d) { const i = process.argv.indexOf(`--${n}`); return i >= 0 ? process.argv[i + 1] : d; }

async function main() {
  const project = arg('project', process.env.GCLOUD_PROJECT);
  initializeApp(project ? { projectId: project } : undefined);
  const email = arg('email');
  const role = arg('role');
  if (!email || !['staff', 'admin', 'device'].includes(role)) {
    throw new Error('need --email and --role staff|admin|device');
  }
  const user = await getAuth().getUserByEmail(email);
  const claims = { role };
  if (role === 'device') {
    claims.device_id = arg('device');
    if (!claims.device_id) throw new Error('--device required for role device');
  }
  await getAuth().setCustomUserClaims(user.uid, claims);
  if (role !== 'device') {
    await getFirestore().doc(`staff/${user.uid}`).set({
      name: arg('name', email), email, role, on_duty: true,
      escalation_order: Number(arg('order', role === 'admin' ? 3 : 1)),
    }, { merge: true });
  }
  console.log(`set ${JSON.stringify(claims)} on ${email} (${user.uid})`);
}

main().catch(e => { console.error(e.message); process.exit(1); });
