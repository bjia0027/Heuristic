#pragma once
#include <functional>
#include <vector>

class Service38 {
public:
    Service38();
    void execute();
    void registerCallback(std::function<void()> cb);
private:
    std::vector<std::function<void()>> callbacks_;
};
