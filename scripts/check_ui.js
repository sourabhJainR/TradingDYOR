const fs = require("node:fs");
const path = require("node:path");

const pages = ["web/index.html", "web/brief.html"];
for (const relative of pages) {
  const filename = path.join(process.cwd(), relative);
  const html = fs.readFileSync(filename, "utf8");
  const ids = [...html.matchAll(/\\bid=["']([^"']+)["']/g)].map(match => match[1]);
  const duplicates = ids.filter((id, index) => ids.indexOf(id) !== index);
  if (duplicates.length) {
    throw new Error(relative + " has duplicate element IDs: " + [...new Set(duplicates)].join(", "));
  }
  const inlineScripts = [...html.matchAll(/<script\\b[^>]*>([\\s\\S]*?)<\\/script>/gi)];
  if (!inlineScripts.length) {
    throw new Error(relative + " has no inline application script");
  }
  for (const [index, match] of inlineScripts.entries()) {
    try {
      new Function(match[1]);
    } catch (error) {
      throw new Error(relative + " inline script " + (index + 1) + " failed syntax validation: " + error.message);
    }
  }
  process.stdout.write("Validated " + relative + ": " + inlineScripts.length + " script(s), unique IDs\\n");
}
