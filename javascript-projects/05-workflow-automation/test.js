#!/usr/bin/env node
/**
 * Test script for workflow automation
 */

const WorkflowEngine = require('./src/WorkflowEngine');
require('dotenv').config();

async function test() {
  console.log('=== AI Workflow Automation - Test ===\n');

  const engine = new WorkflowEngine();

  try {
    console.log('1. Testing Python health check...');
    const healthy = await engine.pythonBridge.healthCheck();
    console.log(`   Health check: ${healthy ? 'PASS' : 'FAIL'}\n`);

    if (!healthy) {
      console.error('   Python environment is not healthy. Exiting.');
      process.exit(1);
    }

    console.log('2. Listing available workflows...');
    const workflows = await engine.listWorkflows();
    console.log(`   Found ${workflows.length} workflow(s):`);
    workflows.forEach(w => {
      console.log(`   - ${w.id}: ${w.name} (${w.steps} steps)`);
    });
    console.log('');

    console.log('3. Executing workflow: file-processor...');
    const execution = await engine.executeWorkflow('examples/file-processor', {});

    console.log(`   Execution ID: ${execution.execution_id}`);
    console.log(`   Status: ${execution.status}`);
    console.log(`   Steps completed: ${execution.steps_completed}`);
    console.log(`   Steps failed: ${execution.steps_failed}`);
    console.log(`   Duration: ${execution.duration_ms}ms`);
    console.log('');

    console.log('4. Execution logs:');
    execution.logs.forEach(log => {
      const time = new Date(log.timestamp).toLocaleTimeString();
      console.log(`   [${time}] [${log.level}] ${log.message}`);
    });
    console.log('');

    if (execution.status === 'completed') {
      console.log('✅ Test completed successfully!');
      process.exit(0);
    } else {
      console.error('❌ Test failed!');
      console.error('Result:', JSON.stringify(execution.result, null, 2));
      process.exit(1);
    }

  } catch (error) {
    console.error('❌ Test error:', error.message);
    process.exit(1);
  }
}

test();
