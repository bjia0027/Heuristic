#pragma once
#include <functional>
#include <vector>

class Service24 {
public:
    Service24();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
