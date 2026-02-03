import React, { useRef, useEffect } from 'react';
import { Box } from '@mui/material';
import MessageBubble from './MessageBubble';
import LoadingIndicator from './LoadingIndicator';
import WelcomeScreen from './WelcomeScreen';

/**
 * Container for chat messages with auto-scroll.
 */
function ChatMessages({
  conversationHistory,
  isLoading,
  pendingUserQuestion,
  currentStep,
  queryResult,
  semanticSearchEnabled,
  vectorCategory,
  onCopy,
  copiedIndex,
  onFollowUpClick,
}) {
  const messagesEndRef = useRef(null);

  // Scroll to bottom when messages update
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [conversationHistory, isLoading]);

  if (conversationHistory.length === 0 && !isLoading) {
    return <WelcomeScreen />;
  }

  return (
    <Box
      sx={{
        flex: 1,
        overflow: 'auto',
        px: 3,
        py: 3,
      }}
    >
      {conversationHistory.map((turn, index) => (
        <MessageBubble
          key={index}
          turn={turn}
          index={index}
          isLatest={index === conversationHistory.length - 1}
          onCopy={onCopy}
          copiedIndex={copiedIndex}
          onFollowUpClick={onFollowUpClick}
        />
      ))}
      {isLoading && (
        <LoadingIndicator
          pendingUserQuestion={pendingUserQuestion}
          currentStep={currentStep}
          queryResult={queryResult}
          semanticSearchEnabled={semanticSearchEnabled}
          vectorCategory={vectorCategory}
        />
      )}
      <div ref={messagesEndRef} />
    </Box>
  );
}

export default ChatMessages;
