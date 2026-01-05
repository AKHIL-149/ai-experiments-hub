#!/usr/bin/env node
/**
 * JavaScript/TypeScript parser helper using esprima
 *
 * This script is called by the Python JavaScriptParser to parse JS/TS files.
 * It outputs JSON to stdout for the Python side to consume.
 */

const fs = require('fs');
const esprima = require('esprima');

// Check for required argument
if (process.argv.length < 3) {
    console.error(JSON.stringify({
        error: 'Usage: node js_parser_helper.js <file_path>'
    }));
    process.exit(1);
}

const filePath = process.argv[2];

// Read and parse the file
try {
    const code = fs.readFileSync(filePath, 'utf-8');

    // Parse with esprima (supports ES6+)
    const ast = esprima.parseModule(code, {
        loc: true,          // Include line/column location info
        comment: true,      // Extract comments
        tolerant: true,     // Continue parsing on errors
        jsx: true          // Support JSX syntax
    });

    // Extract structure from AST
    const result = extractStructure(ast, code);

    // Output JSON to stdout
    console.log(JSON.stringify(result, null, 2));

} catch (error) {
    // Output error as JSON
    console.error(JSON.stringify({
        error: error.message,
        line: error.lineNumber,
        column: error.column
    }));
    process.exit(1);
}

/**
 * Extract code structure from AST
 */
function extractStructure(ast, sourceCode) {
    const structure = {
        imports: [],
        functions: [],
        classes: [],
        exports: [],
        variables: []
    };

    // Walk the AST
    if (ast.body) {
        for (const node of ast.body) {
            processNode(node, structure, sourceCode);
        }
    }

    return structure;
}

/**
 * Process individual AST nodes
 */
function processNode(node, structure, sourceCode) {
    switch (node.type) {
        case 'ImportDeclaration':
            structure.imports.push(extractImport(node));
            break;

        case 'FunctionDeclaration':
            structure.functions.push(extractFunction(node, sourceCode));
            break;

        case 'ClassDeclaration':
            structure.classes.push(extractClass(node, sourceCode));
            break;

        case 'ExportNamedDeclaration':
        case 'ExportDefaultDeclaration':
            structure.exports.push(extractExport(node));
            if (node.declaration) {
                processNode(node.declaration, structure, sourceCode);
            }
            break;

        case 'VariableDeclaration':
            for (const declarator of node.declarations) {
                structure.variables.push({
                    name: declarator.id.name,
                    kind: node.kind, // const, let, var
                    line_number: node.loc ? node.loc.start.line : null,
                    has_init: declarator.init !== null
                });
            }
            break;
    }
}

/**
 * Extract import information
 */
function extractImport(node) {
    const specifiers = node.specifiers.map(spec => {
        if (spec.type === 'ImportDefaultSpecifier') {
            return { name: spec.local.name, alias: null, isDefault: true };
        } else if (spec.type === 'ImportNamespaceSpecifier') {
            return { name: '*', alias: spec.local.name, isNamespace: true };
        } else {
            return {
                name: spec.imported.name,
                alias: spec.local.name !== spec.imported.name ? spec.local.name : null
            };
        }
    });

    return {
        source: node.source.value,
        specifiers: specifiers
    };
}

/**
 * Extract function information
 */
function extractFunction(node, sourceCode, isMethod = false) {
    const func = {
        name: node.id ? node.id.name : '<anonymous>',
        line_number: node.loc ? node.loc.start.line : null,
        end_line: node.loc ? node.loc.end.line : null,
        parameters: extractParameters(node.params),
        is_async: node.async || false,
        is_generator: node.generator || false,
        is_method: isMethod,
        docstring: extractLeadingComment(node, sourceCode)
    };

    // Extract function body summary
    if (node.body && node.body.body) {
        const bodyLines = node.body.body.slice(0, 5).map(stmt => {
            if (node.loc) {
                const lines = sourceCode.split('\n');
                return lines[stmt.loc.start.line - 1]?.trim();
            }
            return null;
        }).filter(Boolean);

        func.body_summary = bodyLines.join('\n');
    }

    return func;
}

/**
 * Extract class information
 */
function extractClass(node, sourceCode) {
    const cls = {
        name: node.id ? node.id.name : '<anonymous>',
        line_number: node.loc ? node.loc.start.line : null,
        end_line: node.loc ? node.loc.end.line : null,
        base_classes: node.superClass ? [node.superClass.name || '<expression>'] : [],
        methods: [],
        properties: [],
        docstring: extractLeadingComment(node, sourceCode)
    };

    // Extract methods and properties
    if (node.body && node.body.body) {
        for (const member of node.body.body) {
            if (member.type === 'MethodDefinition') {
                const method = extractFunction(member.value, sourceCode, true);
                method.name = member.key.name || '<computed>';
                method.kind = member.kind; // 'constructor', 'method', 'get', 'set'
                method.is_static = member.static || false;
                cls.methods.push(method);
            } else if (member.type === 'PropertyDefinition') {
                cls.properties.push({
                    name: member.key.name || '<computed>',
                    is_static: member.static || false,
                    line_number: member.loc ? member.loc.start.line : null
                });
            }
        }
    }

    return cls;
}

/**
 * Extract function parameters
 */
function extractParameters(params) {
    return params.map(param => {
        if (param.type === 'Identifier') {
            return {
                name: param.name,
                default_value: null,
                is_rest: false
            };
        } else if (param.type === 'AssignmentPattern') {
            return {
                name: param.left.name,
                default_value: extractDefaultValue(param.right),
                is_rest: false
            };
        } else if (param.type === 'RestElement') {
            return {
                name: `...${param.argument.name}`,
                default_value: null,
                is_rest: true
            };
        } else {
            return {
                name: '<complex>',
                default_value: null,
                is_rest: false
            };
        }
    });
}

/**
 * Extract default value as string
 */
function extractDefaultValue(node) {
    if (!node) return null;

    switch (node.type) {
        case 'Literal':
            return JSON.stringify(node.value);
        case 'Identifier':
            return node.name;
        case 'ArrayExpression':
            return '[]';
        case 'ObjectExpression':
            return '{}';
        default:
            return '<expression>';
    }
}

/**
 * Extract export information
 */
function extractExport(node) {
    if (node.type === 'ExportDefaultDeclaration') {
        return {
            type: 'default',
            name: node.declaration.id ? node.declaration.id.name : '<anonymous>'
        };
    } else if (node.type === 'ExportNamedDeclaration') {
        const names = [];
        if (node.specifiers) {
            for (const spec of node.specifiers) {
                names.push({
                    name: spec.exported.name,
                    local: spec.local.name
                });
            }
        }
        return {
            type: 'named',
            names: names
        };
    }
    return { type: 'unknown' };
}

/**
 * Extract leading comment (JSDoc style)
 */
function extractLeadingComment(node, sourceCode) {
    if (!node.loc) return null;

    // Look for JSDoc comment immediately before the node
    const lines = sourceCode.split('\n');
    const nodeLine = node.loc.start.line;

    // Check previous lines for comment block
    let commentLines = [];
    let currentLine = nodeLine - 2; // Start one line before node

    while (currentLine >= 0) {
        const line = lines[currentLine].trim();

        if (line.endsWith('*/')) {
            // Found end of comment block, collect it
            commentLines.unshift(line);
            currentLine--;

            while (currentLine >= 0) {
                const commentLine = lines[currentLine].trim();
                commentLines.unshift(commentLine);

                if (commentLine.startsWith('/*') || commentLine.startsWith('/**')) {
                    // Found start of comment
                    return cleanJSDoc(commentLines.join('\n'));
                }
                currentLine--;
            }
            break;
        } else if (line.startsWith('//')) {
            // Single line comment
            commentLines.unshift(line);
            currentLine--;
        } else if (line === '') {
            // Empty line, keep looking
            currentLine--;
        } else {
            // Hit non-comment line
            break;
        }
    }

    if (commentLines.length > 0 && commentLines[0].startsWith('//')) {
        return commentLines.join('\n').replace(/\/\//g, '').trim();
    }

    return null;
}

/**
 * Clean JSDoc comments
 */
function cleanJSDoc(comment) {
    return comment
        .replace(/^\/\*\*?\s*/, '')  // Remove opening /**
        .replace(/\s*\*\/$/, '')      // Remove closing */
        .split('\n')
        .map(line => line.replace(/^\s*\*\s?/, '').trim())  // Remove leading *
        .filter(line => line.length > 0)
        .join('\n');
}
