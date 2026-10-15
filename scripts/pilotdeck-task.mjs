// Thin bootstrap over PilotDeck's native project paths, gateway and CLI channel.
import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const root = process.env.COEVO_PILOTDECK_ROOT;
if (!root) throw new Error('COEVO_PILOTDECK_ROOT must identify the pinned upstream installation');
const upstream = path => import(pathToFileURL(resolve(root, path)));
const { getPilotProjectChatDir, resolvePilotHome } = await upstream('src/pilot/index.ts');
const { createLocalGateway } = await upstream('src/cli/createLocalGateway.ts');
const { CliChannel } = await upstream('src/adapters/channel/cli/CliChannel.ts');
const projectRoot = process.cwd();
const pilotHome = resolvePilotHome(process.env);
const chatDir = getPilotProjectChatDir(projectRoot, pilotHome);
mkdirSync(chatDir, { recursive: true });
writeFileSync(join(dirname(chatDir), '.cwd'), projectRoot + '\n');
const runtime = createLocalGateway({ projectRoot, pilotHome });
try {
  await new CliChannel({ argv: process.argv.slice(2), projectKey: projectRoot, probe: false })
    .start({ gateway: runtime.gateway });
} finally {
  runtime.dispose();
}
