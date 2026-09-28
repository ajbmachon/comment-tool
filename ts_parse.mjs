// Static facts about TypeScript source, read with the TypeScript compiler's parser (no type check).
// Input on stdin: {typescript, file, source, line, scope}. Scope "declaration" (the default): the
// signature of the declaration that starts on the line. Scope "module": the file's exported names.
// Scope "entries": the entries of the list-like literal declared on the line (an array or object
// literal, an enum, or a union type), as {kind: "list", name, entries}. Output on stdout as JSON, or
// {"kind": "none"} when nothing of that shape starts on the line.
import { createRequire } from "node:module";

const input = JSON.parse(await new Promise((resolve) => {
  let text = "";
  process.stdin.on("data", (chunk) => (text += chunk));
  process.stdin.on("end", () => resolve(text));
}));
const ts = createRequire(import.meta.url)(input.typescript);
const source = ts.createSourceFile(input.file, input.source, ts.ScriptTarget.Latest, true);

const lineOf = (node) => source.getLineAndCharacterOfPosition(node.getStart(source)).line + 1;
const textOf = (node) => (node ? node.getText(source) : null);

function findDeclaration(node) {
  if (lineOf(node) === input.line && isDeclaration(node)) return node;
  return ts.forEachChild(node, findDeclaration);
}

function isDeclaration(node) {
  return ts.isFunctionDeclaration(node) || ts.isMethodDeclaration(node) || ts.isClassDeclaration(node)
    || ts.isInterfaceDeclaration(node) || ts.isTypeAliasDeclaration(node) || ts.isEnumDeclaration(node)
    || ts.isVariableStatement(node) || ts.isPropertySignature(node) || ts.isPropertyDeclaration(node)
    || ts.isMethodSignature(node) || ts.isConstructorDeclaration(node) || ts.isExportDeclaration(node);
}

function callableOf(node) {
  if (!ts.isVariableStatement(node)) return node;
  const initializer = node.declarationList.declarations[0]?.initializer;
  return initializer && (ts.isArrowFunction(initializer) || ts.isFunctionExpression(initializer)) ? initializer : null;
}

function nameOf(node) {
  if (ts.isVariableStatement(node)) return textOf(node.declarationList.declarations[0]?.name);
  if (ts.isConstructorDeclaration(node)) return "constructor";
  if (ts.isExportDeclaration(node)) return textOf(node.moduleSpecifier);
  return textOf(node.name);
}

function parameters(callable) {
  return (callable?.parameters ?? []).map((parameter) => ({
    name: textOf(parameter.name),
    type: textOf(parameter.type),
    optional: Boolean(parameter.questionToken || parameter.initializer),
    default: textOf(parameter.initializer),
  }));
}

function failures(node) {
  const found = new Set();
  const visit = (child) => {
    if (ts.isThrowStatement(child) || ts.isYieldExpression(child)) addConstructed(child.expression, found);
    if (ts.isCallExpression(child) && /(^|\.)fail$/.test(textOf(child.expression))) addConstructed(child.arguments[0], found);
    ts.forEachChild(child, visit);
  };
  visit(node);
  return [...found];
}

function addConstructed(expression, found) {
  if (expression && ts.isNewExpression(expression)) found.add(textOf(expression.expression));
}

function effectFailureType(returnType) {
  if (!returnType || !ts.isTypeReferenceNode(returnType) || !/(^|\.)Effect$/.test(textOf(returnType.typeName))) return null;
  return textOf(returnType.typeArguments?.[1]);
}

function members(node) {
  if (ts.isExportDeclaration(node)) {
    return (node.exportClause?.elements ?? []).map((element) => ({ name: textOf(element.name), kind: "ExportSpecifier" }));
  }
  if (!(ts.isClassDeclaration(node) || ts.isInterfaceDeclaration(node))) return [];
  return node.members.map((member) => ({ name: textOf(member.name), kind: ts.SyntaxKind[member.kind] }));
}

function moduleExports() {
  const exported = [];
  for (const statement of source.statements) {
    if (ts.isExportDeclaration(statement)) exported.push(...members(statement));
    else if (/^export\b/.test(textOf(statement))) exported.push({ name: nameOf(statement), kind: ts.SyntaxKind[statement.kind] });
  }
  return exported;
}

function unwrapped(expression) {
  let inner = expression;
  while (inner && (ts.isAsExpression(inner) || ts.isSatisfiesExpression(inner) || ts.isParenthesizedExpression(inner))) {
    inner = inner.expression;
  }
  return inner;
}

function listEntries(node) {
  if (ts.isEnumDeclaration(node)) return node.members;
  if (ts.isTypeAliasDeclaration(node)) return ts.isUnionTypeNode(node.type) ? node.type.types : null;
  if (!ts.isVariableStatement(node)) return null;
  const value = unwrapped(node.declarationList.declarations[0]?.initializer);
  if (value && ts.isArrayLiteralExpression(value)) return value.elements;
  if (value && ts.isObjectLiteralExpression(value)) return value.properties;
  return null;
}

function listLiteral(node) {
  const entries = node ? listEntries(node) : null;
  return entries ? { kind: "list", name: nameOf(node), entries: entries.map(textOf) } : { kind: "none" };
}

const declaration = input.scope === "module" ? null : findDeclaration(source);
if (input.scope === "module") {
  process.stdout.write(JSON.stringify({ kind: "module", exports: moduleExports() }));
} else if (input.scope === "entries") {
  process.stdout.write(JSON.stringify(listLiteral(declaration)));
} else if (!declaration) {
  process.stdout.write(JSON.stringify({ kind: "none" }));
} else {
  const callable = callableOf(declaration);
  const returnType = callable?.type ?? null;
  process.stdout.write(JSON.stringify({
    kind: ts.SyntaxKind[declaration.kind],
    name: nameOf(declaration),
    exported: /^export\b/.test(textOf(declaration)),
    type_parameters: (callable?.typeParameters ?? declaration.typeParameters ?? []).map(textOf),
    parameters: parameters(callable),
    return_type: textOf(returnType),
    declared_type: callable ? null : textOf(declaration.type ?? declaration.declarationList?.declarations[0]?.type),
    failure_type: effectFailureType(returnType),
    thrown_or_failed: callable ? failures(callable) : ts.isClassDeclaration(declaration) ? failures(declaration) : [],
    heritage: (declaration.heritageClauses ?? []).map(textOf),
    members: members(declaration),
  }));
}
