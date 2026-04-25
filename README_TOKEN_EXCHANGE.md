As of April 25, 2026:

FastMCP's built-in OAuth2 server does not support RFC 8693 token exchange natively. Here's the current state:          
                                                                                                                             
  - GitHub issue https://github.com/PrefectHQ/fastmcp/issues/1985 is open requesting exactly this feature. It's labeled as an
   enhancement and is not yet implemented.                                                                                   
  - The FastMCP docs explicitly call out RFC 8693 as the right approach for the on-behalf-of pattern, but you have to        
  implement it yourself.                                                                                                     
                                                                                                                             
  What FastMCP does give you today:                                                                                          
                                                                                                                             
  FastMCP's OAuth proxy handles the client-facing authorization code flow (with PKCE, DCR, etc.) and exposes the upstream    
  access token to your tool functions via get_access_token(). From there, you're on your own to perform the token exchange.
                                                                                                                             
  What you'd need to do yourself:                                                                                          

  1. In your tool handler, call get_access_token() to get the token the MCP client presented.                                
  2. POST to your authorization server's token endpoint with:
    - grant_type=urn:ietf:params:oauth:grant-type:token-exchange                                                             
    - subject_token=<upstream token>                           
    - audience=<downstream service>                                                                                          
    - etc.                                                     
  3. Use the returned exchanged token to call the downstream MCP server.                                                     
  4. Optionally cache the mapping (subject token → exchanged token) to avoid repeated exchanges.                             
                                                                                                                             
  The FastMCP docs warn explicitly against token passthrough (forwarding the original token directly) and the Confused Deputy
   problem — RFC 8693 is the correct fix, but it's manual for now.                                                           
                                                                                                                             
  Sources:                                                     
  - https://github.com/PrefectHQ/fastmcp/issues/1985
  - https://gofastmcp.com/servers/auth/oauth-proxy                                                                           
  -                                               
  https://techcommunity.microsoft.com/blog/azuredevcommunityblog/using-on-behalf-of-flow-for-entra-based-mcp-servers/4486760 
