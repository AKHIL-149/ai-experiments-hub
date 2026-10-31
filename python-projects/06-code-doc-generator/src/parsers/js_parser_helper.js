#!/usr/bin/env node
/**
 * JavaScript/TypeScript parser helper (Babel parser)
 *
 * Called by the Python JavaScriptParser. Reads one file, writes its structure as JSON to stdout.
 * On a syntax error it writes {"error", "line"} as JSON to stderr and exits with 1.
 *
 * Handles modern JavaScript (class fields, private members, optional chaining, top-level await,
 * JSX) and TypeScript (types, interfaces, enums, generics, decorators, parameter properties).
 */

const fs = require('fs');
const path = require('path');

if (process.argv.length < 3) {
    console.error(JSON.stringify({ error: 'Usage: node js_parser_helper.js <file_path>' }));
    process.exit(1);
}

const filePath = process.argv[2];
const extension = path.extname(filePath).toLowerCase();
const isTypeScript = extension === '.ts' || extension === '.tsx' || extension === '.mts' || extension === '.cts';

let parser;
try {
    parser = require('@babel/parser');
} catch (error) {
    console.error(JSON.stringify({ error: "Cannot find module '@babel/parser'" }));
    process.exit(1);
}

let code;
try {
    code = fs.readFileSync(filePath, 'utf-8').replace(/^﻿/, '');
} catch (error) {
    console.error(JSON.stringify({ error: `Cannot read file: ${error.message}` }));
    process.exit(1);
}

// A shebang line (#!/usr/bin/env node) is handled by the parser itself.
const plugins = ['decorators-legacy', 'classProperties', 'classPrivateProperties', 'classPrivateMethods'];
if (isTypeScript) {
    plugins.push('typescript');
    if (extension === '.tsx') plugins.push('jsx');
} else {
    plugins.push('jsx');
}

let ast;
try {
    ast = parser.parse(code, {
        sourceType: 'unambiguous',
        allowReturnOutsideFunction: true,
        allowAwaitOutsideFunction: true,
        allowImportExportEverywhere: true,
        allowSuperOutsideMethod: true,
        plugins,
    });
} catch (error) {
    console.error(JSON.stringify({
        error: String(error.message).replace(/\s*\(\d+:\d+\)\s*$/, ''),
        line: error.loc ? error.loc.line : null,
        column: error.loc ? error.loc.column : null,
    }));
    process.exit(1);
}

const lines = code.split('\n');
console.log(JSON.stringify(extractStructure(ast.program), null, 2));

// ---------------------------------------------------------------------------------------------

function text(node) {
    return node ? code.slice(node.start, node.end) : null;
}

function short(value, limit = 80) {
    if (value === null || value === undefined) return null;
    const flat = value.replace(/\s+/g, ' ').trim();
    return flat.length > limit ? flat.slice(0, limit - 3) + '...' : flat;
}

function startLine(node) {
    return node && node.loc ? node.loc.start.line : null;
}

function extractStructure(program) {
    const structure = {
        language: isTypeScript ? 'typescript' : 'javascript',
        imports: [],
        functions: [],
        classes: [],
        exports: [],
        variables: [],
    };
    for (const node of program.body) {
        processStatement(node, structure, node);
    }
    return structure;
}

/**
 * outer: the statement that carries the comment and decorators (the export wrapper if there is one)
 */
function processStatement(node, structure, outer) {
    switch (node.type) {
        case 'ImportDeclaration':
            structure.imports.push(extractImport(node));
            break;

        case 'FunctionDeclaration':
            structure.functions.push(extractFunction(node, outer));
            break;

        case 'ClassDeclaration':
            structure.classes.push(extractClass(node, outer));
            break;

        case 'TSInterfaceDeclaration':
            structure.classes.push(extractInterface(node, outer));
            break;

        case 'TSEnumDeclaration':
            structure.classes.push(extractEnum(node, outer));
            break;

        case 'TSTypeAliasDeclaration':
            structure.variables.push({
                name: node.id.name, kind: 'type', line_number: startLine(node), has_init: true,
                value: short(text(node.typeAnnotation)),
            });
            break;

        case 'TSModuleDeclaration':
            if (node.body && node.body.body) {
                for (const inner of node.body.body) processStatement(inner, structure, inner);
            }
            break;

        case 'ExportNamedDeclaration':
            if (node.declaration) {
                structure.exports.push({ type: 'named', names: declaredNames(node.declaration) });
                processStatement(node.declaration, structure, node);
            } else {
                structure.exports.push({
                    type: 'named',
                    names: (node.specifiers || []).map(s => ({
                        name: s.exported.name || s.exported.value,
                        local: s.local ? s.local.name : null,
                    })),
                });
            }
            break;

        case 'ExportDefaultDeclaration': {
            const declaration = node.declaration;
            structure.exports.push({
                type: 'default',
                name: declaration.id ? declaration.id.name : (declaration.name || '<anonymous>'),
            });
            if (declaration.type === 'FunctionDeclaration') {
                const func = extractFunction(declaration, node);
                if (!declaration.id) func.name = 'default';
                structure.functions.push(func);
            } else if (declaration.type === 'ClassDeclaration') {
                const cls = extractClass(declaration, node);
                if (!declaration.id) cls.name = 'default';
                structure.classes.push(cls);
            } else if (isFunctionExpression(declaration)) {
                structure.functions.push(extractFunction(declaration, node, 'default'));
            }
            break;
        }

        case 'VariableDeclaration':
            for (const declarator of node.declarations) {
                extractVariable(node, declarator, structure, outer);
            }
            break;

        case 'ExpressionStatement':
            extractCommonJsExport(node, structure);
            break;
    }
}

function declaredNames(declaration) {
    if (declaration.id && declaration.id.name) return [{ name: declaration.id.name, local: declaration.id.name }];
    if (declaration.declarations) {
        return declaration.declarations
            .filter(d => d.id && d.id.name)
            .map(d => ({ name: d.id.name, local: d.id.name }));
    }
    return [];
}

function isFunctionExpression(node) {
    return node && (node.type === 'ArrowFunctionExpression' || node.type === 'FunctionExpression');
}

function extractVariable(declaration, declarator, structure, outer) {
    const init = declarator.init;
    const name = declarator.id && declarator.id.name;
    if (name && isFunctionExpression(init)) {
        // const add = (a, b) => a + b;  /  const add = function (a, b) {...}
        structure.functions.push(extractFunction(init, outer, name));
        return;
    }
    if (name && init && init.type === 'ClassExpression') {
        structure.classes.push(extractClass(init, outer, name));
        return;
    }
    const names = name ? [name] : patternNames(declarator.id);
    for (const each of names) {
        structure.variables.push({
            name: each,
            kind: declaration.kind,
            line_number: startLine(declaration),
            has_init: init !== null && init !== undefined,
            value: short(text(init), 60),
        });
    }
}

function patternNames(pattern) {
    if (!pattern) return [];
    if (pattern.type === 'Identifier') return [pattern.name];
    if (pattern.type === 'ObjectPattern') {
        return pattern.properties.flatMap(p => patternNames(p.type === 'RestElement' ? p.argument : p.value));
    }
    if (pattern.type === 'ArrayPattern') return pattern.elements.flatMap(patternNames);
    if (pattern.type === 'AssignmentPattern') return patternNames(pattern.left);
    if (pattern.type === 'RestElement') return patternNames(pattern.argument);
    return [];
}

/** exports.name = function () {} / module.exports = class {} / module.exports.name = () => {} */
function extractCommonJsExport(statement, structure) {
    const expression = statement.expression;
    if (!expression || expression.type !== 'AssignmentExpression' || expression.operator !== '=') return;
    const target = text(expression.left);
    let name = null;
    if (target === 'module.exports') name = 'module.exports';
    else {
        const match = /^(?:module\.)?exports\.(\w+)$/.exec(target);
        if (match) name = match[1];
    }
    if (!name) return;

    const value = expression.right;
    if (isFunctionExpression(value)) {
        const func = extractFunction(value, statement, value.id ? value.id.name : name);
        structure.functions.push(func);
        structure.exports.push({ type: 'commonjs', name: func.name });
    } else if (value.type === 'ClassExpression') {
        const cls = extractClass(value, statement, value.id ? value.id.name : name);
        structure.classes.push(cls);
        structure.exports.push({ type: 'commonjs', name: cls.name });
    }
}

function extractImport(node) {
    const specifiers = node.specifiers.map(spec => {
        if (spec.type === 'ImportDefaultSpecifier') {
            return { name: spec.local.name, alias: null, isDefault: true };
        }
        if (spec.type === 'ImportNamespaceSpecifier') {
            return { name: '*', alias: spec.local.name, isNamespace: true };
        }
        const imported = spec.imported.name || spec.imported.value;
        return { name: imported, alias: spec.local.name !== imported ? spec.local.name : null };
    });
    return { source: node.source.value, specifiers, type_only: node.importKind === 'type' };
}

// -------------------------------------------------------------------------------- functions

function extractFunction(node, outer, nameOverride) {
    const body = bodyInfo(node);
    return {
        name: nameOverride || (node.id ? node.id.name : '<anonymous>'),
        line_number: startLine(outer || node),
        end_line: node.loc ? node.loc.end.line : null,
        parameters: node.params.map(extractParameter),
        return_type: node.returnType ? short(text(node.returnType.typeAnnotation), 100) : null,
        is_async: !!node.async,
        is_generator: !!node.generator,
        is_method: false,
        decorators: decoratorsOf(outer, node),
        docstring: extractDocComment(outer || node),
        body_summary: body.summary,
        body_lines: body.lines,
    };
}

function extractMethod(member) {
    const method = extractFunction(member, member, memberName(member));
    method.is_method = true;
    method.kind = member.kind;                  // 'constructor', 'method', 'get', 'set'
    method.is_static = !!member.static;
    method.is_abstract = !!member.abstract;
    method.accessibility = member.accessibility || null;
    if (member.type === 'ClassPrivateMethod') method.name = '#' + member.key.id.name;
    return method;
}

function memberName(member) {
    const key = member.key;
    if (!key) return '<unknown>';
    if (member.computed) return `[${short(text(key), 40)}]`;
    if (key.type === 'Identifier') return key.name;
    if (key.type === 'PrivateName') return '#' + key.id.name;
    if (key.type === 'StringLiteral' || key.type === 'NumericLiteral') return String(key.value);
    return short(text(key), 40);
}

/** First lines of the body as written, and how many lines it has (braces not counted) */
function bodyInfo(node) {
    const body = node.body;
    if (!body) return { summary: null, lines: null };
    let first, last;
    if (body.type === 'BlockStatement') {
        first = body.loc.start.line + 1;
        last = body.loc.end.line - 1;
        // "{ return x; }" on one line: the statements share the braces' line
        if (last < first) {
            const inner = code.slice(body.start + 1, body.end - 1).trim();
            return inner ? { summary: inner, lines: 1 } : { summary: null, lines: 0 };
        }
    } else {
        // arrow function with an expression body: just the expression, not the rest of its line
        const expression = text(body).split('\n').filter(line => line.trim() !== '');
        const indent = Math.min(...expression.slice(1).map(line => line.match(/^\s*/)[0].length), Infinity);
        const shown = expression.slice(0, 5).map((line, i) => (i === 0 || indent === Infinity ? line : line.slice(indent)).replace(/\s+$/, ''));
        return { summary: shown.join('\n'), lines: expression.length };
    }
    const kept = lines.slice(first - 1, last).filter(line => line.trim() !== '');
    if (kept.length === 0) return { summary: null, lines: 0 };
    const indent = Math.min(...kept.map(line => line.match(/^\s*/)[0].length));
    const shown = kept.slice(0, 5).map(line => line.slice(indent).replace(/\s+$/, ''));
    return { summary: shown.join('\n'), lines: kept.length };
}

function extractParameter(param) {
    let node = param;
    const info = { name: '<unknown>', type: null, default_value: null, is_rest: false, optional: false };

    if (node.type === 'TSParameterProperty') {       // constructor(private repo: Repo)
        info.accessibility = node.accessibility || (node.readonly ? 'readonly' : null);
        node = node.parameter;
    }
    if (node.type === 'AssignmentPattern') {
        info.default_value = short(text(node.right));
        node = node.left;
    }
    if (node.type === 'RestElement') {
        info.is_rest = true;
        node = node.argument;
    }
    if (node.type === 'Identifier') {
        info.name = node.name;
    } else {
        info.name = short(text(node), 50);            // { a, b } or [x, y]: shown as written
    }
    if (node.optional) info.optional = true;
    if (info.is_rest) info.name = '...' + info.name;
    if (info.optional) info.name += '?';
    const annotation = (node.typeAnnotation || param.typeAnnotation);
    if (annotation && annotation.typeAnnotation) info.type = short(text(annotation.typeAnnotation), 100);
    return info;
}

// ---------------------------------------------------------------------------------- classes

function extractClass(node, outer, nameOverride) {
    const bases = [];
    if (node.superClass) bases.push(short(text(node.superClass), 60));
    for (const impl of node.implements || []) bases.push('implements ' + short(text(impl), 60));

    const cls = {
        name: nameOverride || (node.id ? node.id.name : '<anonymous>'),
        line_number: startLine(outer || node),
        end_line: node.loc ? node.loc.end.line : null,
        base_classes: bases,
        methods: [],
        properties: [],
        decorators: decoratorsOf(outer, node),
        docstring: extractDocComment(outer || node),
    };

    for (const member of node.body.body) {
        switch (member.type) {
            case 'ClassMethod':
            case 'ClassPrivateMethod':
            case 'TSDeclareMethod':
                // an overload signature has no body of its own (the implementation follows); an abstract one is the API
                if (member.type === 'TSDeclareMethod' && !member.abstract) break;
                cls.methods.push(extractMethod(member));
                break;
            case 'ClassProperty':
            case 'ClassPrivateProperty':
            case 'ClassAccessorProperty': {
                const value = member.value;
                if (isFunctionExpression(value)) {          // handler = () => {...} is a method in practice
                    const method = extractFunction(value, member, memberName(member));
                    method.is_method = true;
                    method.kind = 'method';
                    method.is_static = !!member.static;
                    cls.methods.push(method);
                } else {
                    cls.properties.push({
                        name: member.type === 'ClassPrivateProperty' ? '#' + member.key.id.name : memberName(member),
                        type: member.typeAnnotation ? short(text(member.typeAnnotation.typeAnnotation), 100) : null,
                        default_value: short(text(value), 60),
                        is_static: !!member.static,
                        line_number: startLine(member),
                    });
                }
                break;
            }
        }
    }
    return cls;
}

function extractInterface(node, outer) {
    const cls = {
        name: node.id.name,
        line_number: startLine(outer || node),
        end_line: node.loc ? node.loc.end.line : null,
        base_classes: (node.extends || []).map(e => short(text(e), 60)),
        methods: [],
        properties: [],
        decorators: ['interface'],
        docstring: extractDocComment(outer || node),
    };
    for (const member of node.body.body) {
        if (member.type === 'TSMethodSignature') {
            cls.methods.push({
                name: memberName(member),
                line_number: startLine(member),
                end_line: member.loc.end.line,
                parameters: (member.parameters || member.params || []).map(extractParameter),
                return_type: member.typeAnnotation ? short(text(member.typeAnnotation.typeAnnotation), 100) : null,
                is_async: false, is_generator: false, is_method: true, kind: 'method', is_static: false,
                decorators: [], docstring: extractDocComment(member), body_summary: null, body_lines: null,
            });
        } else if (member.type === 'TSPropertySignature') {
            cls.properties.push({
                name: memberName(member),
                type: member.typeAnnotation ? short(text(member.typeAnnotation.typeAnnotation), 100) : null,
                default_value: null,
                is_static: false,
                line_number: startLine(member),
            });
        }
    }
    return cls;
}

function extractEnum(node, outer) {
    return {
        name: node.id.name,
        line_number: startLine(outer || node),
        end_line: node.loc ? node.loc.end.line : null,
        base_classes: [],
        methods: [],
        properties: node.members.map(member => ({
            name: member.id.name || member.id.value,
            type: 'enum constant',
            default_value: short(text(member.initializer), 40),
            is_static: true,
            line_number: startLine(member),
        })),
        decorators: ['enum'],
        docstring: extractDocComment(outer || node),
    };
}

function decoratorsOf(outer, node) {
    const found = (node.decorators || []).concat(outer && outer !== node ? (outer.decorators || []) : []);
    return found.map(d => '@' + short(text(d.expression), 60));
}

// ------------------------------------------------------------------------------- doc comments

/**
 * The comment directly above a node: a /** JSDoc block, or consecutive // lines.
 * A comment separated from the node by a blank line, or a plain block comment, is not its doc.
 */
function extractDocComment(node) {
    const comments = node.leadingComments;
    if (!comments || comments.length === 0) return null;

    const nodeLine = node.loc.start.line;
    const last = comments[comments.length - 1];
    if (last.loc.end.line < nodeLine - 1) return null;

    if (last.type === 'CommentBlock') {
        return last.value.startsWith('*') ? cleanJSDoc(last.value) : null;
    }

    const block = [last];
    for (let i = comments.length - 2; i >= 0; i--) {
        const comment = comments[i];
        if (comment.type !== 'CommentLine' || comment.loc.end.line !== block[0].loc.start.line - 1) break;
        block.unshift(comment);
    }
    return block.map(c => c.value.replace(/^\s?/, '').trimEnd()).join('\n').trim() || null;
}

function cleanJSDoc(value) {
    return value
        .replace(/^\*+/, '')
        .split('\n')
        .map(line => line.replace(/^\s*\*\s?/, '').trim())
        .join('\n')
        .replace(/^\n+|\n+$/g, '')
        .replace(/\n{3,}/g, '\n\n') || null;
}
